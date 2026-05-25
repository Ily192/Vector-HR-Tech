"""API endpoint para encolar runs del sourcer."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.workers.sourcer import run as sourcer_task

router = APIRouter()


class SourcerRunRequest(BaseModel):
    # TODO(cycle-1 task 2.6): extraer empresa_id del run-token en lugar del body.
    # Por ahora es explícito para poder testear sin Paperclip arriba.
    empresa_id: UUID
    vacante_id: UUID | None = None
    icp_text: str | None = None
    target: int = Field(default=50, ge=1, le=200)
    sources: list[str] = Field(default_factory=lambda: ["internal"])
    cost_cap_usd: float | None = Field(default=None, gt=0, le=5.0)


class SourcerRunResponse(BaseModel):
    run_id: UUID
    task_id: str
    status: str


@router.post("/run", response_model=SourcerRunResponse, status_code=202)
async def run_sourcer(req: SourcerRunRequest) -> SourcerRunResponse:
    """Encola un run del sourcer. Async — devuelve task_id para polling."""
    if not req.vacante_id and not req.icp_text:
        raise HTTPException(400, "vacante_id o icp_text es requerido")

    run_id = uuid4()
    cap = req.cost_cap_usd or settings.default_run_cost_cap_usd
    task = sourcer_task.delay(
        run_id=str(run_id),
        empresa_id=str(req.empresa_id),
        vacante_id=str(req.vacante_id) if req.vacante_id else None,
        icp_text=req.icp_text,
        target=req.target,
        sources=req.sources,
        cost_cap_usd=cap,
    )
    return SourcerRunResponse(run_id=run_id, task_id=task.id, status="queued")
