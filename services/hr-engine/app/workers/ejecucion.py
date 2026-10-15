"""Ciclo de vida de un run en Celery, común a todos los agentes.

Lo que antes repetía cada worker:

- `ejecutar_run`: lock del run (idempotencia), presupuesto de gasto con el tope
  grabado al encolar, estado final con el gasto desglosado, y el fallo registrado
  sin tapar la causa. Si no hay proveedor de LLM, deja pasar el error con lo
  gastado para que la tarea aplace.
- `correr_tarea`: el envoltorio síncrono de Celery que aplaza cuando no hay LLM
  (hasta pasar a revisión manual) y reintenta solo los errores transitorios.

El trabajo concreto de cada agente llega como función: el worker solo traduce.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any
from uuid import UUID

from celery import Task

from app.clients.errors import is_transient_error
from app.config import settings
from app.domain.presupuesto import CostBudget
from app.domain.puertos import ProveedorNoDisponibleError
from app.monitoring import bind_log_context, clear_log_context, logger
from app.repositories import runs as runs_repo
from app.workers import run_state

#: El trabajo de un agente: recibe el presupuesto y devuelve (resultado, payload del run).
Trabajo = Callable[[CostBudget], Awaitable[tuple[dict[str, Any], dict[str, Any]]]]


async def ejecutar_run(
    *,
    run_id: str,
    empresa_id: str,
    agent_skill: str,
    cost_cap_usd: float,
    ids: dict[str, str],
    trabajo: Trabajo,
    del_payload: tuple[str, ...] = (),
    sin_guardar: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Si el run ya se ejecutó, devuelve lo guardado: `del_payload` sale del payload
    del run y `sin_guardar` son los campos que no se re-materializan (p. ej. texto
    sobre una persona, que vive en su tabla y no en el result backend)."""
    evento = agent_skill.replace("-", "_")
    bind_log_context(run_id=run_id, empresa_id=empresa_id, agent_skill=agent_skill)
    log = logger.bind(**ids)
    log.info(f"{evento}.run.started")

    # Se crea antes del claim: si el claim revienta, el except lo necesita.
    presupuesto = CostBudget(cap_usd=cost_cap_usd, enforce=settings.enforce_run_cost_cap)
    try:
        claim = await run_state.claim_run(
            run_id=run_id,
            empresa_id=UUID(empresa_id),
            agent_skill=agent_skill,
            cost_cap_usd=cost_cap_usd,
        )
        if claim.outcome is not runs_repo.ClaimOutcome.CLAIMED:
            log.warning(f"{evento}.run.skipped", outcome=str(claim.outcome))
            p = claim.run.payload or {}
            return {
                "run_id": run_id,
                "empresa_id": empresa_id,
                **ids,
                **(sin_guardar or {}),
                **{k: p.get(k) for k in del_payload},
                "cost_usd": round(claim.run.cost_usd, 6),
                "cost_breakdown": {},
                "deduplicated": True,
            }

        # El cap efectivo nunca supera el que quedó grabado al encolar.
        presupuesto.cap_usd = min(cost_cap_usd, claim.run.cost_cap_usd or cost_cap_usd)
        resultado, payload = await trabajo(presupuesto)
        desglose = {k: round(v, 6) for k, v in presupuesto.breakdown.items()}
        await run_state.finish_run(
            run_id=run_id,
            status=runs_repo.STATUS_COMPLETED,
            cost_usd=presupuesto.spent_usd,
            payload={**payload, "cost_breakdown": desglose},
        )
    except ProveedorNoDisponibleError as exc:
        # No es un fallo: la tarea lo aplaza (ver `correr_tarea`).
        exc.cost_usd = presupuesto.spent_usd  # type: ignore[attr-defined]
        raise
    except Exception as exc:
        log.error(
            f"{evento}.run.failed",
            error_type=type(exc).__name__,
            cost_usd=round(presupuesto.spent_usd, 6),
        )
        await run_state.record_failure(run_id=run_id, exc=exc, cost_usd=presupuesto.spent_usd)
        raise
    finally:
        clear_log_context()

    log.info(f"{evento}.run.completed", cost_usd=round(presupuesto.spent_usd, 6))
    return {
        "run_id": run_id,
        "empresa_id": empresa_id,
        **ids,
        **resultado,
        "cost_usd": round(presupuesto.spent_usd, 6),
        "cost_breakdown": desglose,
        "deduplicated": False,
    }


def correr_tarea[R](
    tarea: Task[Any, Any],
    *,
    run_id: str,
    aplazamientos: int,
    evento: str,
    trabajo: Callable[[], Coroutine[Any, Any, R]],
) -> R:
    try:
        return asyncio.run(trabajo())
    except ProveedorNoDisponibleError as exc:
        coste = float(getattr(exc, "cost_usd", 0.0))
        espera = run_state.siguiente_aplazamiento(aplazamientos)
        if espera is None:
            logger.error(f"{evento}.run.manual_review", run_id=run_id, aplazamientos=aplazamientos)
            asyncio.run(run_state.send_to_manual_review(run_id=run_id, exc=exc, cost_usd=coste))
            raise
        asyncio.run(
            run_state.defer_run(
                run_id=run_id, exc=exc, cost_usd=coste, aplazamiento=aplazamientos + 1
            )
        )
        logger.warning(
            f"{evento}.run.aplazada",
            run_id=run_id,
            en_segundos=espera,
            aplazamiento=aplazamientos + 1,
        )
        raise tarea.retry(
            exc=exc,
            countdown=espera,
            kwargs={**(tarea.request.kwargs or {}), "aplazamientos": aplazamientos + 1},
            # Los aplazamientos no gastan el cupo de reintentos transitorios.
            max_retries=(tarea.request.retries or 0) + 1,
        ) from exc
    except Exception as exc:
        retries = tarea.request.retries or 0
        if is_transient_error(exc) and retries < (tarea.max_retries or 0):
            logger.warning(
                f"{evento}.run.retrying",
                run_id=run_id,
                attempt=retries + 1,
                error_type=type(exc).__name__,
            )
            raise tarea.retry(exc=exc, countdown=run_state.retry_countdown(retries)) from exc
        raise
