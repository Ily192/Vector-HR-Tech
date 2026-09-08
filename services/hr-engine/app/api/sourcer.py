"""API endpoint para encolar runs del sourcer.

Auth: run-token de Paperclip (ADR-005). `empresa_id`, `run_id` y `cost_cap_usd`
salen SIEMPRE del token firmado; el body solo lleva parámetros de negocio.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field

from app.api.common import RunAcceptedResponse, RunRequestBase, register_run
from app.api.rate_limit import RUN_RATE_LIMIT, limiter
from app.database import DbSession, TenantId
from app.monitoring import logger
from app.repositories import runs as runs_repo
from app.security.run_token import RunTokenClaims, require_sourcer_token
from app.workers.sourcer import run as sourcer_task

router = APIRouter()

AGENT_SKILL = "sourcer"


class SourcerRunRequest(RunRequestBase):
    """Parámetros de negocio del run.

    NO acepta `empresa_id` ni `cost_cap_usd`: vienen del run-token. Si llegan
    en el body se ignoran (ver `RunRequestBase`).
    """

    vacante_id: UUID | None = None
    icp_text: str | None = None
    target: int = Field(default=50, ge=1, le=200)
    sources: list[str] = Field(default_factory=lambda: ["internal"])


@router.post(
    "/run",
    response_model=RunAcceptedResponse,
    status_code=202,
    summary="Encola un run del sourcer",
)
@limiter.limit(RUN_RATE_LIMIT)
async def run_sourcer(
    request: Request,
    response: Response,
    req: SourcerRunRequest,
    db: DbSession,
    claims: Annotated[RunTokenClaims, Depends(require_sourcer_token)],
    empresa_id: TenantId,
) -> RunAcceptedResponse:
    """Encola un run del sourcer. Async — devuelve task_id para polling."""
    if not req.vacante_id and not req.icp_text:
        raise HTTPException(400, "vacante_id o icp_text es requerido")

    run_id = claims.run_id
    cost_cap = claims.effective_cost_cap_usd

    created = await register_run(
        db,
        claims=claims,
        agent_skill=AGENT_SKILL,
        payload={
            "vacante_id": str(req.vacante_id) if req.vacante_id else None,
            "target": req.target,
            "sources": req.sources,
        },
    )
    if not created:
        existing = await runs_repo.get_run(db, run_id)
        logger.info("sourcer.run.duplicate", run_id=str(run_id))
        return RunAcceptedResponse(
            run_id=run_id,
            task_id=None,
            status=existing.status if existing else runs_repo.STATUS_PENDING,
            empresa_id=empresa_id,
            cost_cap_usd=cost_cap,
            deduplicated=True,
        )

    task = sourcer_task.delay(
        run_id=str(run_id),
        empresa_id=str(empresa_id),
        vacante_id=str(req.vacante_id) if req.vacante_id else None,
        icp_text=req.icp_text,
        target=req.target,
        sources=req.sources,
        cost_cap_usd=cost_cap,
    )
    logger.info(
        "sourcer.run.queued",
        run_id=str(run_id),
        task_id=task.id,
        empresa_id=str(empresa_id),
        cost_cap_usd=cost_cap,
    )
    return RunAcceptedResponse(
        run_id=run_id,
        task_id=task.id,
        status="queued",
        empresa_id=empresa_id,
        cost_cap_usd=cost_cap,
    )
