"""Ciclo de vida de la fila `runs` desde los workers.

Todas las operaciones abren su PROPIA sesión, deliberadamente sin
`set_tenant_context`: la tabla `runs` solo tiene política RLS `for select`, así
que bajo el rol `authenticated` un INSERT falla y un UPDATE matchea 0 filas
(exactamente el bug que hacía que `update_run_status` fuera un no-op).
El aislamiento por tenant se mantiene comparando el `empresa_id` del run-token
contra la fila (`claim_run` filtra por `empresa_id`).

Sesión aparte también significa transacción aparte: si la transacción de
dominio explota y hace rollback, el `status='failed'` igual queda persistido.
"""

from __future__ import annotations

import random
from typing import Any
from uuid import UUID

from app.config import settings
from app.database import db_session
from app.repositories import runs as runs_repo

#: Margen sobre el time limit antes de considerar un run `running` como colgado.
_STALE_MARGIN_SECONDS = 60


def stale_after_seconds() -> int:
    return settings.celery_task_time_limit + _STALE_MARGIN_SECONDS


async def claim_run(
    *,
    run_id: str,
    empresa_id: UUID | str,
    agent_skill: str,
    cost_cap_usd: float,
) -> runs_repo.RunClaim:
    """Toma el lock del run (idempotencia ante redelivery de Celery)."""
    async with db_session() as db:
        claim = await runs_repo.claim_run(
            db,
            run_id=run_id,
            empresa_id=empresa_id,
            agent_skill=agent_skill,
            cost_cap_usd=cost_cap_usd,
            stale_after_seconds=stale_after_seconds(),
        )
        await db.commit()
        return claim


async def finish_run(
    *,
    run_id: str,
    status: str,
    cost_usd: float,
    payload: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    """Persiste el estado final del run. Lanza `RunNotFoundError` si no existe."""
    async with db_session() as db:
        await runs_repo.update_run_status(
            db,
            run_id=run_id,
            status=status,
            cost_usd=cost_usd,
            payload=payload,
            error_message=error_message,
        )
        await db.commit()


def retry_countdown(retries: int, *, base: int = 5, cap: int = 60) -> int:
    """Backoff exponencial con jitter para `self.retry()`."""
    delay = min(base * (2**retries), cap)
    return max(1, int(delay * random.uniform(0.5, 1.0)))


def truncate_error(exc: BaseException, *, limit: int = 500) -> str:
    """Mensaje de error acotado y sin traceback para `runs.error_message`."""
    return f"{type(exc).__name__}: {exc}"[:limit]
