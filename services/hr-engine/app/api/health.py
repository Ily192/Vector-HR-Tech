"""Liveness + readiness.

`/ready` chequea Postgres **y** Redis: el broker es lo que hace fallar el 100%
de los POST /run (encolar es lo primero que hace el endpoint), así que un
readiness que solo mirara la DB dejaba entrar tráfico a un servicio inútil.
"""

from __future__ import annotations

import asyncio
from typing import Literal

import redis.asyncio as aioredis
from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from app.config import settings
from app.database import db_session
from app.monitoring import logger

router = APIRouter()

_PING_TIMEOUT_SECONDS = 5.0


class ReadinessResponse(BaseModel):
    status: Literal["ready", "degraded"]
    postgres: Literal["ok", "error"]
    redis: Literal["ok", "error"]


@router.get("/health", tags=["health"])
async def liveness() -> dict[str, str]:
    """Liveness probe — proceso vivo. No toca dependencias externas."""
    return {"status": "ok"}


async def _check_postgres() -> bool:
    try:
        async with asyncio.timeout(_PING_TIMEOUT_SECONDS), db_session() as db:
            await db.execute(text("select 1"))
        return True
    except Exception as exc:
        logger.warning("ready.postgres_down", error_type=type(exc).__name__)
        return False


async def _check_redis() -> bool:
    client = aioredis.from_url(
        settings.redis_url,
        socket_connect_timeout=_PING_TIMEOUT_SECONDS,
        socket_timeout=_PING_TIMEOUT_SECONDS,
    )
    try:
        async with asyncio.timeout(_PING_TIMEOUT_SECONDS):
            await client.ping()
        return True
    except Exception as exc:
        logger.warning("ready.redis_down", error_type=type(exc).__name__)
        return False
    finally:
        await client.aclose()


@router.get("/ready", tags=["health"], response_model=ReadinessResponse)
async def readiness(response: Response) -> ReadinessResponse:
    """Readiness probe — Postgres + Redis (broker Celery) alcanzables."""
    postgres_ok, redis_ok = await asyncio.gather(_check_postgres(), _check_redis())
    ready = postgres_ok and redis_ok
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if ready else "degraded",
        postgres="ok" if postgres_ok else "error",
        redis="ok" if redis_ok else "error",
    )
