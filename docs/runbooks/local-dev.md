# Runbook · Local development

## Comandos diarios

```bash
# Arrancar todo
docker compose -f infra/docker/docker-compose.dev.yml up -d
pnpm dev                                                    # frontends + packages
cd services/hr-engine && uv run uvicorn app.main:app --reload  # API
uv run celery -A app.workers.celery_app worker --loglevel=info # worker

# Detener
docker compose -f infra/docker/docker-compose.dev.yml down
```

## Reset completo

Si algo está roto y quieres arrancar limpio:

```bash
docker compose -f infra/docker/docker-compose.dev.yml down -v   # -v borra volumes
rm -rf node_modules .turbo apps/*/node_modules apps/*/.next packages/*/node_modules
rm -rf services/hr-engine/.venv

pnpm install
pnpm tokens:build

cd services/hr-engine && uv sync --dev
```

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

### CORS errors en frontend

Editar `apps/<app>/.env` y agregar tu URL local a `allow_origins` en `services/hr-engine/app/main.py`.
