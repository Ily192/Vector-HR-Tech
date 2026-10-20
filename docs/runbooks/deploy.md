# Runbook · Deploy

> **⚠️ ESTADO REAL (2026-09-07): este runbook describe un sistema que todavia
> no existe.** Leelo como el diseño objetivo, no como instrucciones ejecutables.
>
> Lo que si funciona hoy:
> - Frontends: se despliegan por la integracion Git de Vercel, con la config de
>   `apps/*/vercel.json`. Los proyectos aun no estan provisionados.
>
> Lo que NO existe:
> - **No hay entorno de staging.** `staging.vortex-ops.com` y
>   `api.vortex-ops.com` no estan provisionados.
> - **Los comandos de Coolify de abajo** apuntan a una plataforma que ADR-012
>   descarto en favor de Fly.io; los secrets `COOLIFY_*` no existen y no se van a
>   crear. El backend se despliega en Fly.io: ver "hr-engine en Fly.io (MVP)".
> - **`release.yml` esta desactivado** (solo `workflow_dispatch`) justamente
>   porque intentaba ejecutar esto en cada push a `main`.
> - **El canary no existe.** Los `curl` con `canary_pct` son un JSON inventado:
>   Coolify no tiene traffic-splitting, y no hay balanceador ni service mesh en
>   ninguna parte del repo.
> - **Alembic no esta configurado**: no hay `alembic.ini` ni directorio de
>   migraciones. El esquema real son los `.sql` de `infra/supabase/migrations/`,
>   aplicados con `supabase db push`. Cualquier `alembic upgrade head` de aqui
>   abajo es aspiracional.
>
> Antes de un primer deploy real hay que cerrar esto; ver
> `docs/runbooks/next-steps.md`.

## hr-engine en Fly.io (MVP)

Esto sí existe desde el 2026-10-20: `services/hr-engine/fly.toml` y el workflow
`deploy-hr-engine.yml` (ADR-012). Una sola app con la misma imagen y tres grupos
de procesos:

| Proceso | Qué hace | Máquinas |
|---|---|---|
| `api` | FastAPI; responde `/ready` y se apaga sin tráfico | 0 o 1 |
| `worker` | Celery: la coincidencia de skills del plan gratis (ADR-019) | 1 |
| `beat` | Programa el barrido cada minuto y la purga diaria | **exactamente 1** |

Dos `beat` programan cada tarea dos veces. Por eso el workflow despliega con
`--ha=false` y el conteo se fija a mano una vez.

La imagen no se construye con `fly deploy`: el Dockerfile pide el contexto con
nombre `skills` (`.agents/skills`) y flyctl no lo pasa. El workflow la construye con
buildx, la sube a `registry.fly.io` y despliega con `fly deploy --image`.

### Primer despliegue (una vez)

1. `fly auth login` y `fly apps create vortex-hr-engine` (la región, `gru`, está en
   `fly.toml`).
2. Redis: Upstash (`fly redis create` o su consola). La URL con TLS lleva
   `?ssl_cert_reqs=required`: Celery no acepta una `rediss://` sin ese parámetro.
3. Secretos, con `fly secrets set -a vortex-hr-engine NOMBRE=valor …`:
   - `DATABASE_URL`: el pooler de Supabase en modo sesión, puerto 5432:
     `postgresql+asyncpg://postgres.<ref>:<contraseña>@aws-0-sa-east-1.pooler.supabase.com:5432/postgres`.
     El modo transacción (6543) no admite los prepared statements de asyncpg.
   - `REDIS_URL` y `RATE_LIMIT_STORAGE_URI`: la URL de Redis.
   - `JWT_SECRET`: 32 caracteres o más (`openssl rand -hex 32`).
   - `CORS_ALLOW_ORIGINS`: las URLs del panel y del career site, separadas por coma.
   - `SUPABASE_URL` y `SUPABASE_SECRET_KEY`: para bajar los CVs.
   - Opcional: `SENTRY_DSN_BACKEND`. Las claves de Gemini y OpenAI llegan con el
     plan de pago.

   `ENV=production` ya va en `fly.toml`: con él, el arranque falla si falta algo de lo
   anterior o apunta a localhost (`app/config.py`).
4. Token para GitHub: `fly tokens create deploy -a vortex-hr-engine`, y guardarlo
   como el secret `FLY_API_TOKEN` del repo (Settings → Secrets and variables → Actions).
5. Actions → "Deploy hr-engine (Fly.io)" → *Run workflow*.
6. `fly scale count api=1 worker=1 beat=1 -a vortex-hr-engine --yes` y comprobar con
   `fly status` que hay un solo `beat`.
7. Verificar: `curl https://vortex-hr-engine.fly.dev/ready` responde
   `{"status":"ready","postgres":"ok","redis":"ok"}`, y `fly logs` muestra un
   `coincidencias.barrido` por minuto.

### Despliegues siguientes y vuelta atrás

- Desplegar: el mismo workflow, desde la rama `main`.
- Volver atrás: `fly releases -a vortex-hr-engine` y
  `fly deploy --app vortex-hr-engine --image registry.fly.io/vortex-hr-engine:<sha anterior>`.
  Cada imagen queda etiquetada con el commit.

### Costo

El worker y el beat quedan encendidos; la API se apaga sin tráfico. Es la máquina
fija que estima ADR-019 (~US$8 al mes). Celery con Redis consulta la cola todo el
tiempo: el plan gratis de Upstash puede quedarse corto. Revisar el consumo la
primera semana.

## Staging (automático)

Cualquier merge a `main` dispara `release.yml`:

```
build-images → deploy-staging → smoke-staging → promote-canary 5% → monitor 10min → promote-full
```

Si cualquier paso falla, no avanza. Sentry registra release SHA automáticamente.

## Producción (canary 5% → 100%)

Configurado en `release.yml`. Manual override si necesario:

```bash
# Promote 100% inmediato (usar con cuidado)
curl -X POST $COOLIFY_WEBHOOK_PROD \
  -H "Authorization: Bearer $COOLIFY_TOKEN" \
  -d '{"sha":"<sha>","canary_pct":100}'
```

## Migrations DB

**Patrón expand/contract obligatorio** para zero-downtime:

1. PR 1: Migration **expand** (agrega columnas/tablas, no rompe).
2. PR 1 deploy: app escribe a viejo + nuevo.
3. PR 2: Backfill data (si aplica).
4. PR 3: Migration que cambia reads a nuevo path.
5. PR 4: Migration **contract** (drop viejo).

Antes de mergear migration:

```bash
# Dry-run en staging
DATABASE_URL=$STAGING_DATABASE_URL alembic upgrade head --sql > /tmp/migration.sql
# Revisar /tmp/migration.sql humano

# Aplicar staging
DATABASE_URL=$STAGING_DATABASE_URL alembic upgrade head

# Verificar smoke staging verde
gh run watch
```

## Rollback

| Tipo | Cómo |
|---|---|
| Frontend Vercel | Promote previous deployment desde dashboard Vercel (~1 min) |
| Backend Coolify | `coolify rollback <service> --to <sha>` (~5 min) |
| Migration buena → app mala | Solo rollback del service. Migration queda. |
| Migration mala | Re-run down-migration (dry-run primero). Si imposible: PITR. |
| Datos corruptos | Supabase PITR — Settings → Database → PITR (≤ 30 min RTO) |

## Post-deploy checklist

- [ ] Sentry sin spike de errors en 10 min post-deploy.
- [ ] OTel p95 latency dentro de baseline +30%.
- [ ] Synthetic monitors verdes.
- [ ] DORA dashboard actualizado (auto via nightly).

## Si todo falla (Sev-1)

1. Pause deploys nuevos: label `deploy-frozen` en repo.
2. Rollback servicio afectado.
3. Comunicar en `/status` page.
4. Postmortem en ≤ 14 días en `docs/runbooks/postmortems/`.
