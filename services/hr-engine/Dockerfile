# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# uv for fast deps
COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /usr/local/bin/uv

WORKDIR /app

# uv.lock SIN glob: si falta, el build tiene que fallar acá y no en runtime.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY . .
RUN uv sync --frozen --no-dev

# ───────── runtime ─────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# non-root user
RUN useradd -r -u 1000 -m vortex
COPY --from=builder --chown=vortex:vortex /app /app
USER vortex

EXPOSE 8000

# /ready (no /health): /health devuelve una constante y el contenedor figuraría
# "sano" con Postgres o Redis caídos — y sin broker falla el 100% de los POST.
# start-period cubre el arranque en frio del pool de conexiones.
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/ready || exit 1

# default = api; override en docker-compose para worker
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
