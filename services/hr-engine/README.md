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
├── api/               Endpoints HTTP (+ rate_limit.py, common.py)
├── clients/           LLMs (openai, google-genai) + errors.py (retryables)
├── repositories/      SQL raw: hr.py (dominio) + runs.py (estado de runs)
├── security/          run_token.py (ADR-005) + tenant_context.py (RLS)
└── workers/           Celery tasks — patrón _run + @task wrapper
```

## Convenciones

- Cada worker = `async def _run(...)` testeable + `@celery_app.task` wrapper con
  `bind=True` y `self.retry()` solo para errores transitorios.
- Settings tipadas. Nada de `os.getenv` suelto.
- Logs JSON estructurados con `structlog`. **Sin PII**: nombres y salidas crudas
  de LLM se hashean con `monitoring.hash_pii`.
- Idempotencia obligatoria en workers: la fila `runs` es el lock (`claim_run`).
- Tipos estrictos (`mypy --strict` en CI).
