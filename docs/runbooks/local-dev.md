# Runbook · Local development

## Requisitos

- Node 20 (`.nvmrc`) y pnpm 9 — `corepack enable pnpm` si no lo tienes.
- Python 3.12 y [`uv`](https://docs.astral.sh/uv/).
- Docker con backend Linux funcionando. En Windows eso significa **WSL2
  instalado con una distro**: sin distro, Docker Desktop arranca pero su engine
  Linux nunca responde y `docker ps` devuelve 500. `wsl --install` y reiniciar.

## Comandos diarios

```bash
# Stack completo (Postgres + Redis + hr-engine API + worker Celery)
docker compose -f infra/docker/docker-compose.dev.yml up -d
pnpm dev    # frontends + packages

# Detener
docker compose -f infra/docker/docker-compose.dev.yml down
```

El compose ya incluye `hr-engine-api` y `hr-engine-worker`. Si prefieres correr
el backend fuera de Docker para tener reload:

```bash
docker compose -f infra/docker/docker-compose.dev.yml up -d postgres redis
cd services/hr-engine
uv run uvicorn app.main:app --reload                          # API
uv run celery -A app.workers.celery_app worker --loglevel=info # worker
```

## Dos entornos locales, no los mezcles

| | `docker compose` | Supabase CLI |
|---|---|---|
| Puerto Postgres | 5432 (`vortex_dev`) | 54322 (`postgres`) |
| Auth / Storage | no | sí |
| Schema `auth` | shim de `infra/docker/initdb/` | real |

Para todo lo que toque signup, JWT hooks, Storage o policies de `anon`, usa el
Supabase CLI: el shim del compose es una aproximación mínima y no reproduce
GoTrue. Ver `infra/supabase/README.md`.

## Reset completo

Si algo está roto y quieres arrancar limpio:

```bash
docker compose -f infra/docker/docker-compose.dev.yml down -v   # -v borra volumes
rm -rf node_modules .turbo apps/*/node_modules apps/*/.next packages/*/node_modules
rm -rf services/hr-engine/.venv

pnpm install
pnpm tokens:build

cd services/hr-engine && uv sync
```

El `down -v` es importante: los scripts de `/docker-entrypoint-initdb.d/` solo
corren en la primera inicialización del volumen. Sin borrarlo, una migración
nueva no se aplica y no hay ningún aviso.

## Errores comunes

### `psql: ERROR: extension "vector" does not exist`

La imagen Postgres oficial no trae pgvector. Estamos usando `pgvector/pgvector:pg15`. Verifica `infra/docker/docker-compose.dev.yml`.

### `Module not found: Can't resolve '@vortex/ui'`

Olvidaste correr `pnpm install` o el workspace no está en `pnpm-workspace.yaml`. Verifica:

```yaml
# pnpm-workspace.yaml
packages:
  - "apps/*"
  - "packages/*"
```

### `OperationalError: could not connect to Postgres`

Compose no levantó. Revisa `docker compose ps` y logs.

### Celery worker no recibe tasks

- ¿Redis arriba? `redis-cli ping`
- ¿`REDIS_URL` apuntando al mismo en API y worker?
- ¿Worker en la queue correcta (`--queues=hr`)?

### `database "vortex_dev" ... relation "empresas" does not exist`

El contenedor arrancó pero el esquema no se aplicó. Casi siempre es porque el
volumen ya existía de un `up` anterior: los scripts de init solo corren la
primera vez. `docker compose ... down -v` y volver a levantar.

Si es un contenedor nuevo, mira `docker compose logs postgres`: si el shim
`00_supabase_shim.sql` no corrió antes que `10_0001_...`, la migración falla al
referenciar `auth.users` y el entrypoint aborta.

### CORS errors en frontend

Ajusta `CORS_ALLOW_ORIGINS` en `services/hr-engine/.env` (coma-separado). Antes
esto estaba hardcodeado en `app/main.py`.
