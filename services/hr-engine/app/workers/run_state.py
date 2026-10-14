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
from app.monitoring import logger
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


async def record_failure(*, run_id: str, exc: BaseException, cost_usd: float) -> None:
    """Deja el run en `failed` sin tapar la excepción original.

    El caller re-lanza `exc`, que es la causa real. Si el registro en sí falla
    —Postgres caído, run inexistente, sesión sin permisos— se loguea y se
    traga: una excepción lanzada desde un `except` sustituye a la original y
    con ella se pierde el diagnóstico.
    """
    try:
        await finish_run(
            run_id=run_id,
            status=runs_repo.STATUS_FAILED,
            cost_usd=cost_usd,
            error_message=truncate_error(exc),
        )
    except Exception as registro_exc:
        logger.error(
            "run.failure_not_recorded",
            run_id=run_id,
            error_type=type(registro_exc).__name__,
            original_error_type=type(exc).__name__,
        )


#: Esperas entre aplazamientos cuando no hay ningún LLM disponible (~1 h en total).
#: Todas por debajo de CELERY_VISIBILITY_TIMEOUT (900 s): con Redis como broker,
#: una tarea programada más allá de ese plazo se entrega dos veces. Lo vigila un test.
APLAZAMIENTOS_S: tuple[int, ...] = (120, 300, 600, 840, 840, 840)


def siguiente_aplazamiento(hechos: int) -> int | None:
    """Segundos hasta el próximo intento, o None si ya se agotaron."""
    return APLAZAMIENTOS_S[hechos] if hechos < len(APLAZAMIENTOS_S) else None


async def defer_run(*, run_id: str, exc: BaseException, cost_usd: float, aplazamiento: int) -> None:
    """La evaluación espera a que vuelva el LLM: el run vuelve a `pending` con el porqué.

    La candidatura ya está guardada; lo único que se retrasa es su evaluación.
    """
    try:
        await finish_run(
            run_id=run_id,
            status=runs_repo.STATUS_PENDING,
            cost_usd=cost_usd,
            error_message=(
                f"Esperando a que vuelva el LLM (aplazamiento {aplazamiento} de "
                f"{len(APLAZAMIENTOS_S)}): {truncate_error(exc)}"
            ),
            payload={"esperando_llm": True, "aplazamientos": aplazamiento},
        )
    except Exception as registro_exc:
        logger.error(
            "run.defer_not_recorded", run_id=run_id, error_type=type(registro_exc).__name__
        )


async def send_to_manual_review(*, run_id: str, exc: BaseException, cost_usd: float) -> None:
    """Tras agotar los aplazamientos: `failed` + `needs_manual_review`, para que una
    persona la evalúe. El proceso de selección no se queda esperando para siempre."""
    try:
        await finish_run(
            run_id=run_id,
            status=runs_repo.STATUS_FAILED,
            cost_usd=cost_usd,
            error_message=(
                "Sin LLM disponible tras ~1 h de reintentos: pasa a revisión manual. "
                + truncate_error(exc)
            )[:500],
            payload={"needs_manual_review": True, "esperando_llm": False},
        )
    except Exception as registro_exc:
        logger.error(
            "run.manual_review_not_recorded", run_id=run_id, error_type=type(registro_exc).__name__
        )


def retry_countdown(retries: int, *, base: int = 5, cap: int = 60) -> int:
    """Backoff exponencial con jitter para `self.retry()`."""
    delay = min(base * (2**retries), cap)
    return max(1, int(delay * random.uniform(0.5, 1.0)))


def truncate_error(exc: BaseException, *, limit: int = 500) -> str:
    """Mensaje de error acotado y sin traceback para `runs.error_message`."""
    return f"{type(exc).__name__}: {exc}"[:limit]
