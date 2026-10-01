"""Async SQLAlchemy session factories + tenant_guard middleware helper.

Hay DOS motores a propósito, porque la API y los workers viven en loops
distintos. Ver `_make_engine`.
"""

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
from sqlalchemy.pool import NullPool

from app.config import settings


def _make_engine(*, pooled: bool) -> AsyncEngine:
    """Motor async. `pooled=False` para quien abra un event loop por tarea.

    Una conexión asyncpg queda atada al event loop en el que nació. La API corre
    sobre un solo loop y le saca partido al pool. Cada tarea de Celery, en
    cambio, hace su propio `asyncio.run()`: el loop muere al terminar la tarea,
    pero el pool se queda la conexión, y la tarea siguiente la recibe apuntando
    a un loop cerrado. Muere con `RuntimeError: Event loop is closed` y, como el
    fallo ocurre al tomar la conexión, ni siquiera llega a registrarse el run.

    La documentación oficial de SQLAlchemy 2.0 —la versión del lockfile— lo
    resuelve en «Using multiple asyncio event loops»: "If the same engine must
    be shared between different loop, it should be configured to disable
    pooling using NullPool, preventing the Engine from using any connection
    more than once".
    https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-multiple-asyncio-event-loops
    """
    if not pooled:
        # NullPool abre y cierra la conexión dentro del mismo loop, así que no
        # hay nada que reciclar: `pool_size`, `max_overflow`, `pool_timeout` y
        # `pool_pre_ping` no aplican (create_async_engine los rechaza).
        return create_async_engine(
            settings.database_url,
            poolclass=NullPool,
            echo=settings.env == "development",
            connect_args={"timeout": 10, "command_timeout": 30},
        )
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


#: API: un solo event loop para todo el proceso, el pool es una ventaja.
_api_engine = _make_engine(pooled=True)
#: Workers Celery: un event loop por tarea, el pool es un bug.
_worker_engine = _make_engine(pooled=False)

_session_factory = async_sessionmaker(_api_engine, class_=AsyncSession, expire_on_commit=False)
_worker_session_factory = async_sessionmaker(
    _worker_engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def api_session() -> AsyncIterator[AsyncSession]:
    """Sesión sobre el motor con pool. Para código del proceso de la API que no
    pasa por `Depends` (el readiness probe), que así comprueba el pool real.
    """
    async with _session_factory() as session:
        yield session


@asynccontextmanager
async def db_session() -> AsyncIterator[AsyncSession]:
    """Sesión SIN pool, para los workers de Celery (un event loop por tarea)."""
    async with _worker_session_factory() as session:
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
