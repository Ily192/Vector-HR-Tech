# hr-engine

Vortex Ops · HR execution engine (FastAPI + Celery).

## Local dev

```bash
cd services/hr-engine
cp .env.example .env

# Asume Postgres + Redis corriendo (ver infra/docker/docker-compose.dev.yml)
# Las herramientas de dev viven en [dependency-groups] (PEP 735): `uv sync`
# las instala por defecto, sin flags.
uv sync

# API
uv run uvicorn app.main:app --reload --port 8000

# Worker (otra terminal)
uv run celery -A app.workers.celery_app worker --loglevel=info --queues=hr
```

API en http://localhost:8000/docs

## Auth: run-tokens (ADR-005)

`POST /api/sourcer/run` y `POST /api/cv-evaluator/run` exigen un **run-token**
JWT emitido por Paperclip:

```
Authorization: Bearer <run-token>
```

Claims (espejo de `packages/types/src/tenant.ts::RunTokenClaimsSchema`):

```json
{
  "empresa_id": "uuid",
  "agent_skill": "sourcer",
  "run_id": "uuid",
  "cost_cap_usd": 0.05,
  "exp": 1746710000
}
```

Reglas:

| Situación                                  | Respuesta |
| ------------------------------------------ | --------- |
| Sin header `Authorization`                  | 401       |
| Firma inválida / token malformado           | 401       |
| `exp` vencido                               | 401       |
| Claims que no cumplen el schema             | 401       |
| `agent_skill` ≠ skill del endpoint          | 403       |
| `run_id` ya usado por otro tenant           | 409       |
| Token válido                                | 202       |

- **`empresa_id`, `run_id` y `cost_cap_usd` salen SIEMPRE del token.** Si el
  body los trae, se ignoran en silencio (`extra="ignore"`).
- El `cost_cap_usd` del token se recorta a `MAX_RUN_COST_CAP_USD` (techo duro
  del engine).
- Para pruebas locales podés emitir uno con
  `app.security.run_token.issue_run_token(...)`.

## Variables de entorno

Ver `.env.example` (nombres alineados con la raíz del monorepo). Las que más
suelen morderte:

| Variable                      | Por qué importa |
| ----------------------------- | --------------- |
| `JWT_SECRET`                  | Firma de run-tokens. En `ENV=production` el arranque **falla** si es un placeholder o mide < 32 chars. |
| `CORS_ALLOW_ORIGINS`          | CSV de orígenes. En producción no puede traer `localhost` ni `*` con credenciales. |
| `RATE_LIMIT_STORAGE_URI`      | Obligatorio en producción: en memoria el límite no se comparte entre workers. |
| `SENTRY_DSN_BACKEND`          | Nombre canónico (la raíz lo define así). `SENTRY_DSN` se acepta como alias legacy. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Nombre canónico. `OTEL_ENDPOINT` se acepta como alias legacy. Vacío = OTel desactivado. |
| `CELERY_VISIBILITY_TIMEOUT`   | Debe ser > `CELERY_TASK_TIME_LIMIT` o Redis re-entrega tasks en vuelo. |

`ENV=production` valida todo eso al construir `Settings`: si algo está mal, el
proceso no arranca (mejor que descubrirlo con tráfico real encima).

## Alta de una empresa

Vector HR da de alta a cada empresa del plan gratis y la invita al panel:

```bash
uv run python -m app.cli.alta_empresa --empresa "Ferretería Norte" \
    --correo ana@ferreterianorte.mx --nombre "Ana Ruiz" --tamano 35
uv run python -m app.cli.alta_empresa --reenviar ana@ferreterianorte.mx
```

Crea la empresa con plan gratis y una invitación de un solo uso (en la base solo
queda el hash del token), y Supabase Auth manda el correo; el enlace deja a la
persona dentro del panel. Si el correo no sale, no queda nada a medias. El enlace
dura una hora: `--reenviar` manda otro a quien no ha entrado, y también puede pedir
uno desde la pantalla de entrar del panel. Necesita `DATABASE_URL` (el rol dueño),
`SUPABASE_URL`, `SUPABASE_SECRET_KEY` y `PANEL_URL`.

## Evaluación con IA del plan de pago (ADR-021)

**Qué hace:**
- **Cuándo:** un barrido de Celery beat (`evaluaciones.barrer`, cada minuto).
- **Qué evalúa:** cada aplicación de las empresas `ia`, con el texto del CV anonimizado (`domain/anonimizacion.py`).
- **El resultado:** la aplicación pasa a "Evaluados".
- **Registro:** no lleva run-token. Cada evaluación deja su fila en `runs` con su costo.

**Para correrlo:**
- **Beat:** corre con un solo beat (`uv run celery -A app.workers.celery_app beat`) y el worker.
- **Variables:** necesita `GOOGLE_API_KEY` del nivel de pago (en el gratuito, Google usa los prompts para mejorar sus productos), `SUPABASE_URL` y `SUPABASE_SECRET_KEY`.
- **Topes:**
  - `empresas.ia_cvs_por_mes`: 1.000 por defecto; lo ajusta Vector HR.
  - `IA_PRESUPUESTO_MENSUAL_USD`: US$25 para toda la plataforma.
  - Al llegar a un tope, las aplicaciones esperan; nada más se detiene.
- **Lote:** `EVALUACIONES_LOTE` dice cuántas toma cada barrido y `EVALUACIONES_EN_PARALELO`, cuántas puntúa a la vez.
- **Fallas:** tras 3 intentos sin éxito, la aplicación queda "sin evaluar" para revisarla a mano.

## Despliegue

En el VPS, con el resto de la plataforma (ADR-020): la API, el worker y un solo beat
salen de la misma imagen en `infra/vps/compose.yml`, y el workflow `deploy-vps.yml` la
construye con el contexto `skills`. Primer despliegue y secretos: `docs/runbooks/vps.md`.
El alta de una empresa en producción es el mismo comando dentro del contenedor:
`vortex exec hr-engine-api python -m app.cli.alta_empresa …`.

## Salud

- `GET /health` — liveness. Constante, no toca dependencias.
- `GET /ready` — readiness: **Postgres + Redis**. 503 si alguno está caído.
  Es el que usa el `HEALTHCHECK` del Dockerfile.

## Tests

```bash
uv run pytest tests/unit -q --cov=app --cov-report=term
uv run pytest tests/security -q    # requiere Postgres real (RLS)
```

## Estructura

```
app/
├── main.py            FastAPI app + request-id + exception handlers
├── config.py          Settings tipadas + hardening de producción
├── database.py        Async session factory + tenant_guard
├── monitoring.py      structlog + Sentry + OTel + hash_pii
├── domain/            Entidades, políticas y puertos de la evaluación (solo stdlib)
├── application/       Casos de uso sobre los puertos del dominio (EvaluateCandidate, EvaluarAplicacionesPendientes, CoincidirCvsPendientes, DarDeAltaEmpresa)
├── infrastructure/    Adaptadores de los puertos (SQL, OpenAI, Gemini) y cola por nombre
├── api/               Endpoints HTTP (+ rate_limit.py, common.py)
├── cli/               Comandos para el equipo de Vector HR (alta_empresa.py)
├── clients/           LLMs (openai, google-genai) + errors.py (retryables)
├── repositories/      SQL raw: hr.py (dominio) + runs.py (estado de runs)
├── security/          run_token.py (ADR-005) + tenant_context.py (RLS)
└── workers/           Tareas de Celery finas + ejecucion.py (ciclo de vida del run)
```

## Convenciones

- Regla de dependencias: `domain/` solo importa la stdlib, y `application/` la
  stdlib y el dominio. Lo comprueba `tests/unit/test_regla_de_dependencias.py`.
- Cada worker traduce la petición y llama a su caso de uso dentro de
  `ejecucion.ejecutar_run` (lock, presupuesto, estado final); la tarea de Celery
  delega en `ejecucion.correr_tarea` (aplaza sin LLM, reintenta solo lo transitorio).
- La API encola por nombre (`app/infrastructure/cola.py`) y no importa los workers.
- El SQL vive en `app/repositories`; lo comprueba `tests/unit/test_infraestructura.py`.
- Settings tipadas. Nada de `os.getenv` suelto.
- Logs JSON estructurados con `structlog`. **Sin PII**: nombres y salidas crudas
  de LLM se hashean con `monitoring.hash_pii`.
- Idempotencia obligatoria en workers: la fila `runs` es el lock (`claim_run`).
- Tipos estrictos (`mypy --strict` en CI).
