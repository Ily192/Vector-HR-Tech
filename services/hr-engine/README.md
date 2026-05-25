# hr-engine

Vortex Ops · HR execution engine (FastAPI + Celery).

## Local dev

```bash
cd services/hr-engine
cp .env.example .env

# Asume Postgres + Redis corriendo (ver infra/docker/docker-compose.dev.yml)
uv sync --dev

# API
uv run uvicorn app.main:app --reload --port 8000

# Worker (otra terminal)
uv run celery -A app.workers.celery_app worker --loglevel=info --queues=hr
```

API en http://localhost:8000/docs

## Tests

```bash
uv run pytest tests/unit -v
uv run pytest tests/integration -v   # requiere Postgres + Redis
```

## Estructura

```
app/
├── main.py            FastAPI app
├── config.py          Settings tipadas
├── database.py        Async session factory + tenant_guard
├── monitoring.py      Sentry + structlog + OTel
├── api/               Endpoints HTTP
├── models/            SQLAlchemy (cycle 1)
├── schemas/           Pydantic (cycle 1)
├── services/          Lógica de negocio
├── providers/         Adaptadores externos (cycle 1: gemini, supabase_vec, scraper)
└── workers/           Celery tasks — patrón _run + @task wrapper
```

## Convenciones

- Cada worker = `async def _run(...)` testeable + `@celery_app.task` wrapper.
- Settings tipadas. Nada de `os.getenv` suelto.
- Logs JSON estructurados con `structlog`.
- Idempotencia obligatoria en workers que tocan APIs externas.
- Tipos estrictos (`mypy --strict` en CI).
