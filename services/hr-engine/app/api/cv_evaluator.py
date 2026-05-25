"""API endpoint para encolar runs del cv_evaluator (single candidato↔vacante)."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.config import settings
from app.workers.cv_evaluator import run as cv_evaluator_task

router = APIRouter()


class CvEvaluatorRunRequest(BaseModel):
    empresa_id: UUID
    vacante_id: UUID
    candidato_id: UUID
    cost_cap_usd: float | None = Field(default=None, gt=0, le=5.0)


class CvEvaluatorRunResponse(BaseModel):
    run_id: UUID
    task_id: str
    status: str


@router.post("/run", response_model=CvEvaluatorRunResponse, status_code=202)
async def run_cv_evaluator(req: CvEvaluatorRunRequest) -> CvEvaluatorRunResponse:
    run_id = uuid4()
    cap = req.cost_cap_usd or settings.default_run_cost_cap_usd
    task = cv_evaluator_task.delay(
        run_id=str(run_id),
        empresa_id=str(req.empresa_id),
        vacante_id=str(req.vacante_id),
        candidato_id=str(req.candidato_id),
        cost_cap_usd=cap,
    )
    return CvEvaluatorRunResponse(run_id=run_id, task_id=task.id, status="queued")
