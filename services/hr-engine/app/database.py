"""Async SQLAlchemy session factory + tenant_guard middleware helper."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings


def _make_engine() -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_timeout=10,
        echo=settings.env == "development",
        # Sin esto un Postgres inalcanzable cuelga el request hasta el timeout
        # del SO (minutos).
        connect_args={"timeout": 10, "command_timeout": 30},
    )


def _make_session() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(_make_engine(), class_=AsyncSession, expire_on_commit=False)


_session_factory = _make_session()


async def get_db() -> AsyncIterator[AsyncSession]:
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def db_session() -> AsyncIterator[AsyncSession]:
    """Para uso fuera de FastAPI (workers Celery)."""
    async with _session_factory() as session:
        yield session


def tenant_guard(request: Request) -> UUID:
    """Defensa en profundidad: `empresa_id` verificado del run-token.

    `app.security.run_token.RunTokenAuth` deja el `empresa_id` del token firmado
    en `request.state`. Esta dependencia lo re-lee para que ningún endpoint
    pueda usar un `empresa_id` que no haya pasado por verificación de firma
    (antes existía pero NINGÚN endpoint la usaba).
    """
    empresa_id = getattr(request.state, "empresa_id", None)
    if empresa_id is None:
        raise HTTPException(
            status_code=401,
            detail="Tenant context missing — falta un run-token válido",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not isinstance(empresa_id, UUID):
        empresa_id = UUID(str(empresa_id))
    return empresa_id


TenantId = Annotated[UUID, Depends(tenant_guard)]
DbSession = Annotated[AsyncSession, Depends(get_db)]
