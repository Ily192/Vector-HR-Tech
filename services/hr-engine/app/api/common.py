"""Piezas compartidas por los endpoints que encolan runs."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.monitoring import logger
from app.repositories import runs as runs_repo
from app.security.run_token import RunTokenClaims


class RunRequestBase(BaseModel):
    """Base de los bodies de `/run`.

    `extra="ignore"`: si un cliente viejo sigue mandando `empresa_id` o
    `cost_cap_usd` en el body, se DESCARTAN en silencio. Esos dos valores solo
    pueden venir del run-token firmado (ADR-005) — aceptarlos del body era el
    agujero que permitía lanzar runs contra cualquier tenant y con el cost cap
    que se te ocurriera.
    """

    model_config = ConfigDict(extra="ignore")


class RunAcceptedResponse(BaseModel):
    run_id: UUID
    task_id: str | None
    status: str
    empresa_id: UUID
    cost_cap_usd: float
    deduplicated: bool = False


async def register_run(
    db: AsyncSession,
    *,
    claims: RunTokenClaims,
    agent_skill: str,
    payload: dict[str, Any] | None = None,
) -> bool:
    """Crea la fila `runs` en estado `pending` ANTES de encolar.

    Sin esto el worker hacía `UPDATE runs WHERE id = :run_id` contra una fila
    inexistente: 0 filas afectadas, sin error, y el costo del run nunca se
    persistía.

    Returns:
        True si la creó; False si el run ya existía (run-token reenviado) —
        en ese caso NO hay que volver a encolar.
    """
    try:
        created = await runs_repo.create_run(
            db,
            run_id=claims.run_id,
            empresa_id=claims.empresa_id,
            agent_skill=agent_skill,
            cost_cap_usd=claims.effective_cost_cap_usd,
            payload=payload,
        )
    except runs_repo.TenantMismatchError as exc:
        logger.warning(
            "run.tenant_mismatch",
            run_id=str(claims.run_id),
            empresa_id=str(claims.empresa_id),
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    # Commit explícito: el worker puede tomar la task antes de que termine el
    # request, y necesita ver la fila.
    await db.commit()
    return created
