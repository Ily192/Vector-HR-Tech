"""API endpoint para encolar runs del cv_evaluator (single candidato↔vacante).

Auth: run-token de Paperclip (ADR-005) con `agent_skill = "cv-evaluator"`.
Un token emitido para `sourcer` recibe 403 acá.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from app.api.common import RunAcceptedResponse, RunRequestBase, register_run
from app.api.rate_limit import RUN_RATE_LIMIT, limiter
from app.database import DbSession, TenantId
from app.monitoring import logger
from app.repositories import runs as runs_repo
from app.security.run_token import RunTokenClaims, require_cv_evaluator_token
from app.workers.cv_evaluator import run as cv_evaluator_task

router = APIRouter()

AGENT_SKILL = "cv-evaluator"


class CvEvaluatorRunRequest(RunRequestBase):
    """`empresa_id` y `cost_cap_usd` NO se aceptan del body (ver RunRequestBase)."""

    vacante_id: UUID
    candidato_id: UUID


@router.post(
    "/run",
    response_model=RunAcceptedResponse,
    status_code=202,
    summary="Encola una evaluación candidato↔vacante",
)
@limiter.limit(RUN_RATE_LIMIT)
async def run_cv_evaluator(
    request: Request,
    response: Response,
    req: CvEvaluatorRunRequest,
    db: DbSession,
    claims: Annotated[RunTokenClaims, Depends(require_cv_evaluator_token)],
    empresa_id: TenantId,
) -> RunAcceptedResponse:
    run_id = claims.run_id
    cost_cap = claims.effective_cost_cap_usd

    created = await register_run(
        db,
        claims=claims,
        agent_skill=AGENT_SKILL,
        payload={
            "vacante_id": str(req.vacante_id),
            "candidato_id": str(req.candidato_id),
        },
    )
    if not created:
        existing = await runs_repo.get_run(db, run_id)
        logger.info("cv_evaluator.run.duplicate", run_id=str(run_id))
        return RunAcceptedResponse(
            run_id=run_id,
            task_id=None,
            status=existing.status if existing else runs_repo.STATUS_PENDING,
            empresa_id=empresa_id,
            cost_cap_usd=cost_cap,
            deduplicated=True,
        )

    task = cv_evaluator_task.delay(
        run_id=str(run_id),
        empresa_id=str(empresa_id),
        vacante_id=str(req.vacante_id),
        candidato_id=str(req.candidato_id),
        cost_cap_usd=cost_cap,
    )
    logger.info(
        "cv_evaluator.run.queued",
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
