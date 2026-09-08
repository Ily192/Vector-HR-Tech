"""Repository de la tabla `runs` — espejo local del control plane (Paperclip).

Esta tabla es el estado canónico local de una ejecución: se crea al ENCOLAR
(antes existía solo un `uuid4()` en memoria, así que el `UPDATE runs` del worker
matcheaba 0 filas y el cost tracking nunca se persistía) y se usa además como
lock de idempotencia para el redelivery de Celery (`task_acks_late=True`).

⚠️ RLS — estado actual y decisión pendiente.

Este docstring decía que `runs` solo tenía política `for select`, así que un
INSERT bajo `authenticated` fallaba y un UPDATE matcheaba 0 filas. **Eso dejó
de ser cierto en `0004_security_hardening.sql`**, que añadió `runs_tenant_write`.
Verificado contra Postgres real: `tests/security/test_rls.py::
test_worker_can_persist_run_status` inserta y actualiza un run bajo
`authenticated` con contexto de tenant, y afecta 1 fila.

Hoy conviven por tanto DOS caminos válidos y solo uno debería sobrevivir:

  1. **Sesión sin contexto de tenant** (lo que hace este módulo hoy). El
     aislamiento lo garantiza la aplicación: el `empresa_id` viene del
     run-token firmado y se compara contra la fila. Simple, pero la base no
     tiene forma de atrapar un error de esa comparación.
  2. **Sesión con `set_tenant_context`**, apoyada en `runs_tenant_write`. Es
     lo que pide ADR-004 (defensa en profundidad): el motor deniega el
     cross-tenant aunque el código se equivoque.

(2) es la dirección correcta, pero mover el worker a contexto de tenant toca
`app/workers/run_state.py` y el ciclo de vida de la sesión, así que se decide y
se ejecuta aparte. Mientras tanto estas funciones SIGUEN necesitando una sesión
sin `set_tenant_context` — no por falta de policy, sino porque el `empresa_id`
del contexto no está seteado en ese punto del flujo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Estados posibles de un run.
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

TERMINAL_STATUSES = frozenset({STATUS_COMPLETED, STATUS_FAILED})


class RunNotFoundError(RuntimeError):
    """El UPDATE de `runs` no afectó ninguna fila.

    Antes esto pasaba SIEMPRE y en silencio. Ahora es un error visible: o el
    run no existe, o RLS lo está ocultando (sesión con rol equivocado).
    """


class TenantMismatchError(RuntimeError):
    """El run existe pero pertenece a otro tenant. Nunca debería pasar."""


class ClaimOutcome(StrEnum):
    """Resultado de intentar tomar el lock de un run."""

    CLAIMED = "claimed"
    ALREADY_COMPLETED = "already_completed"
    IN_PROGRESS = "in_progress"


@dataclass(slots=True, frozen=True)
class RunRow:
    id: UUID
    empresa_id: UUID
    agent_skill: str
    status: str
    cost_usd: float
    cost_cap_usd: float | None
    error_message: str | None
    payload: dict[str, Any] | None


@dataclass(slots=True, frozen=True)
class RunClaim:
    outcome: ClaimOutcome
    run: RunRow


def _row_to_run(row: Any) -> RunRow:
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return RunRow(
        id=row["id"],
        empresa_id=row["empresa_id"],
        agent_skill=row["agent_skill"],
        status=row["status"],
        cost_usd=float(row["cost_usd"] or 0),
        cost_cap_usd=float(row["cost_cap_usd"]) if row["cost_cap_usd"] is not None else None,
        error_message=row["error_message"],
        payload=payload,
    )


_SELECT_COLUMNS = """
    id, empresa_id, agent_skill, status, cost_usd, cost_cap_usd,
    error_message, payload
"""


async def get_run(db: AsyncSession, run_id: UUID | str) -> RunRow | None:
    row = (
        (
            await db.execute(
                text(f"select {_SELECT_COLUMNS} from runs where id = :id"),
                {"id": str(run_id)},
            )
        )
        .mappings()
        .first()
    )
    return _row_to_run(row) if row else None


async def create_run(
    db: AsyncSession,
    *,
    run_id: UUID | str,
    empresa_id: UUID | str,
    agent_skill: str,
    cost_cap_usd: float,
    payload: dict[str, Any] | None = None,
) -> bool:
    """Crea la fila `runs` en estado `pending`. Idempotente por `id`.

    Returns:
        True si la creó, False si ya existía (mismo run-token reutilizado).

    Raises:
        TenantMismatchError: el `run_id` ya existe bajo otro tenant.
    """
    created = (
        (
            await db.execute(
                text(
                    """
                insert into runs (id, empresa_id, agent_skill, status,
                                  cost_usd, cost_cap_usd, payload)
                values (:id, :empresa_id, :agent_skill, 'pending',
                        0, :cost_cap_usd, cast(:payload as jsonb))
                on conflict (id) do nothing
                returning id
                """,
                ),
                {
                    "id": str(run_id),
                    "empresa_id": str(empresa_id),
                    "agent_skill": agent_skill,
                    "cost_cap_usd": cost_cap_usd,
                    "payload": json.dumps(payload) if payload else None,
                },
            )
        )
        .mappings()
        .first()
    )
    if created:
        return True

    existing = await get_run(db, run_id)
    if existing is not None and str(existing.empresa_id) != str(empresa_id):
        raise TenantMismatchError(
            f"run {run_id} pertenece a otro tenant — posible replay de run-token",
        )
    return False


async def claim_run(
    db: AsyncSession,
    *,
    run_id: UUID | str,
    empresa_id: UUID | str,
    agent_skill: str,
    cost_cap_usd: float,
    stale_after_seconds: int,
) -> RunClaim:
    """Toma el lock del run para ejecutarlo (idempotencia ante redelivery).

    Transiciones permitidas → `running`:
      - `pending`  : primera ejecución.
      - `failed`   : reintento de Celery.
      - `running`  : solo si quedó colgado más de `stale_after_seconds`
                     (worker muerto con `task_reject_on_worker_lost=True`).

    Si el run ya está `completed`, NO se re-ejecuta: devolvemos
    `ALREADY_COMPLETED` y el worker corta antes de gastar un solo token de LLM.

    Crea la fila si no existe (ruta de invocación directa a Celery, p. ej. un
    replay manual), para que el estado nunca quede huérfano.
    """
    await create_run(
        db,
        run_id=run_id,
        empresa_id=empresa_id,
        agent_skill=agent_skill,
        cost_cap_usd=cost_cap_usd,
    )

    claimed = (
        (
            await db.execute(
                text(
                    f"""
                update runs
                   set status = 'running',
                       started_at = now(),
                       finished_at = null,
                       error_message = null
                 where id = :id
                   and empresa_id = :empresa_id
                   and (
                        status in ('pending', 'failed')
                        or (status = 'running'
                            and started_at < now() - make_interval(secs => :stale))
                   )
                returning {_SELECT_COLUMNS}
                """,
                ),
                {
                    "id": str(run_id),
                    "empresa_id": str(empresa_id),
                    "stale": stale_after_seconds,
                },
            )
        )
        .mappings()
        .first()
    )
    if claimed:
        return RunClaim(outcome=ClaimOutcome.CLAIMED, run=_row_to_run(claimed))

    current = await get_run(db, run_id)
    if current is None:
        raise RunNotFoundError(f"run {run_id} no existe tras intentar crearlo")
    if str(current.empresa_id) != str(empresa_id):
        raise TenantMismatchError(f"run {run_id} pertenece a otro tenant")
    outcome = (
        ClaimOutcome.ALREADY_COMPLETED
        if current.status == STATUS_COMPLETED
        else ClaimOutcome.IN_PROGRESS
    )
    return RunClaim(outcome=outcome, run=current)


async def update_run_status(
    db: AsyncSession,
    *,
    run_id: UUID | str,
    status: str,
    cost_usd: float,
    payload: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    """Actualiza la fila de `runs` y VERIFICA que haya afectado una fila.

    Raises:
        RunNotFoundError: el UPDATE matcheó 0 filas (run inexistente o RLS).
    """
    updated = (
        (
            await db.execute(
                text(
                    """
                update runs
                   set status = :status,
                       cost_usd = :cost_usd,
                       finished_at = case
                           when :status in ('completed', 'failed') then now()
                           else finished_at
                       end,
                       error_message = :error_message,
                       payload = coalesce(cast(:payload as jsonb), payload)
                 where id = :run_id
                returning id
                """,
                ),
                {
                    "run_id": str(run_id),
                    "status": status,
                    "cost_usd": cost_usd,
                    "error_message": error_message,
                    "payload": json.dumps(payload) if payload else None,
                },
            )
        )
        .mappings()
        .first()
    )
    if updated is None:
        raise RunNotFoundError(
            f"update_run_status no afectó filas para run {run_id} "
            f"(¿fila inexistente o sesión con rol restringido por RLS?)",
        )
