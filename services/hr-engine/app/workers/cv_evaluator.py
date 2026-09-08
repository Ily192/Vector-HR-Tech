"""CV evaluator worker — evalúa un candidato↔vacante específico.

Diferencia vs sourcer:
- Sourcer: batch sobre N candidatos top-K vector.
- CV evaluator: single (candidato_id, vacante_id) — usado cuando un candidato
  aplica desde career-site (paso 1 del pipeline post-apply).

Pipeline:
  1. Toma el lock del run (`runs`) — idempotencia ante redelivery.
  2. Lee candidato + vacante (ambas tienen que estar bajo el mismo tenant).
  3. Si la vacante no tiene embedding o el candidato no tiene cv_embedding,
     los genera.
  4. Score con Gemini Flash (mismo schema que sourcer).
  5. Upsert application status='evaluated' + persiste costo/estado en `runs`.

Output strict schema: `app.clients.scoring.CandidateFitResponse` que mirror-ea
`packages/types/src/hr.ts::CvEvaluationSchema`.
"""

from __future__ import annotations

import asyncio
from typing import Any, TypedDict
from uuid import UUID

from celery import Task
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.embeddings import embed_text
from app.clients.errors import is_transient_error
from app.clients.scoring import score_candidate_fit
from app.database import db_session
from app.monitoring import bind_log_context, clear_log_context, logger
from app.repositories import hr as hr_repo
from app.repositories import runs as runs_repo
from app.security.tenant_context import set_tenant_context
from app.workers import run_state
from app.workers.celery_app import celery_app
from app.workers.cost_tracker import CostCapExceededError, CostTracker

AGENT_SKILL = "cv-evaluator"


class CvEvaluatorResult(TypedDict):
    run_id: str
    empresa_id: str
    vacante_id: str
    candidato_id: str
    application_id: str
    score: float
    rationale: str
    gaps: list[str]
    strengths: list[str]
    recommended_next_step: str
    cost_usd: float
    cost_breakdown: dict[str, float]
    deduplicated: bool


async def _get_candidato_text(db: AsyncSession, candidato_id: UUID) -> tuple[str, str | None]:
    """Devuelve (texto_para_embedding, summary_para_scoring)."""
    row = (
        (
            await db.execute(
                text(
                    """
                select full_name, headline, summary, cv_embedding::text as emb
                  from candidatos
                 where id = :id
                """,
                ),
                {"id": str(candidato_id)},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise ValueError(f"candidato {candidato_id} no existe (o RLS lo oculta)")
    parts = [row["full_name"], row["headline"] or "", row["summary"] or ""]
    return "\n".join(p for p in parts if p), row["emb"]


async def _ensure_candidato_embedding(
    db: AsyncSession,
    candidato_id: UUID,
    text_to_embed: str,
    cost_tracker: CostTracker,
) -> None:
    cost_tracker.assert_under_cap()
    emb = await embed_text(text_to_embed)
    cost_tracker.add(emb.cost_usd, "embedding_candidato")
    await db.execute(
        text(
            """
            update candidatos
               set cv_embedding = cast(:emb as vector),
                   updated_at = now()
             where id = :id
            """,
        ),
        {
            "id": str(candidato_id),
            "emb": "[" + ",".join(f"{v:.7f}" for v in emb.vector) + "]",
        },
    )


def _deduplicated_result(
    *,
    run_id: str,
    empresa_id: UUID,
    vacante_id: UUID,
    candidato_id: UUID,
    run: runs_repo.RunRow,
) -> CvEvaluatorResult:
    """Resultado slim de un run ya ejecutado.

    El rationale/gaps NO se re-materializan: viven en `applications` y no
    queremos duplicar texto sobre una persona en el result backend.
    """
    payload = run.payload or {}
    return {
        "run_id": run_id,
        "empresa_id": str(empresa_id),
        "vacante_id": str(vacante_id),
        "candidato_id": str(candidato_id),
        "application_id": str(payload.get("application_id", "")),
        "score": float(payload.get("score", 0.0)),
        "rationale": "",
        "gaps": [],
        "strengths": [],
        "recommended_next_step": str(payload.get("recommended_next_step", "")),
        "cost_usd": round(run.cost_usd, 6),
        "cost_breakdown": {},
        "deduplicated": True,
    }


async def _run(
    *,
    run_id: str,
    empresa_id: str,
    vacante_id: str,
    candidato_id: str,
    cost_cap_usd: float = 0.05,
) -> CvEvaluatorResult:
    bind_log_context(run_id=run_id, empresa_id=empresa_id, agent_skill=AGENT_SKILL)
    log = logger.bind(
        run_id=run_id,
        empresa_id=empresa_id,
        agent_skill=AGENT_SKILL,
        vacante_id=vacante_id,
        candidato_id=candidato_id,
    )
    log.info("cv_evaluator.run.started")

    empresa_uuid = UUID(empresa_id)
    vacante_uuid = UUID(vacante_id)
    candidato_uuid = UUID(candidato_id)

    claim = await run_state.claim_run(
        run_id=run_id,
        empresa_id=empresa_uuid,
        agent_skill=AGENT_SKILL,
        cost_cap_usd=cost_cap_usd,
    )
    if claim.outcome is not runs_repo.ClaimOutcome.CLAIMED:
        log.warning("cv_evaluator.run.skipped", outcome=str(claim.outcome))
        clear_log_context()
        return _deduplicated_result(
            run_id=run_id,
            empresa_id=empresa_uuid,
            vacante_id=vacante_uuid,
            candidato_id=candidato_uuid,
            run=claim.run,
        )

    effective_cap = min(cost_cap_usd, claim.run.cost_cap_usd or cost_cap_usd)
    cost_tracker = CostTracker(cap_usd=effective_cap)

    try:
        async with db_session() as db:
            await set_tenant_context(db, empresa_uuid, role="HR")

            vacante = await hr_repo.get_vacante(db, vacante_uuid)
            if vacante is None:
                raise ValueError(f"vacante {vacante_uuid} no existe (o RLS la oculta)")
            icp_source = vacante.icp_text or vacante.jd

            if not vacante.icp_embedding:
                cost_tracker.assert_under_cap()
                emb = await embed_text(icp_source)
                cost_tracker.add(emb.cost_usd, "embedding_icp")
                await hr_repo.update_vacante_embedding(db, vacante_uuid, emb.vector)

            cand_text, cand_emb = await _get_candidato_text(db, candidato_uuid)
            if not cand_emb:
                await _ensure_candidato_embedding(db, candidato_uuid, cand_text, cost_tracker)

            cost_tracker.assert_under_cap()
            scoring = await score_candidate_fit(
                {
                    "full_name": cand_text.splitlines()[0] if cand_text else None,
                    "headline": None,
                    "summary": cand_text,
                },
                icp_source,
            )
            cost_tracker.add(scoring.cost_usd, "scoring")

            application_id = await hr_repo.upsert_application(
                db,
                empresa_id=empresa_uuid,
                vacante_id=vacante_uuid,
                candidato_id=candidato_uuid,
                fit_score=scoring.response.score,
                fit_rationale=scoring.response.rationale,
                fit_gaps=list(scoring.response.gaps),
            )
            await db.commit()

        await run_state.finish_run(
            run_id=run_id,
            status=runs_repo.STATUS_COMPLETED,
            cost_usd=cost_tracker.spent_usd,
            payload={
                "score": scoring.response.score,
                "application_id": str(application_id),
                "recommended_next_step": scoring.response.recommended_next_step,
            },
        )
    except Exception as exc:
        log.error(
            "cv_evaluator.run.failed",
            error_type=type(exc).__name__,
            cost_usd=round(cost_tracker.spent_usd, 6),
        )
        await run_state.finish_run(
            run_id=run_id,
            status=runs_repo.STATUS_FAILED,
            cost_usd=cost_tracker.spent_usd,
            error_message=run_state.truncate_error(exc),
        )
        raise
    finally:
        clear_log_context()

    result: CvEvaluatorResult = {
        "run_id": run_id,
        "empresa_id": str(empresa_uuid),
        "vacante_id": str(vacante_uuid),
        "candidato_id": str(candidato_uuid),
        "application_id": str(application_id),
        "score": scoring.response.score,
        "rationale": scoring.response.rationale,
        "gaps": list(scoring.response.gaps),
        "strengths": list(scoring.response.strengths),
        "recommended_next_step": scoring.response.recommended_next_step,
        "cost_usd": round(cost_tracker.spent_usd, 6),
        "cost_breakdown": {k: round(v, 6) for k, v in cost_tracker.breakdown.items()},
        "deduplicated": False,
    }
    log.info(
        "cv_evaluator.run.completed",
        score=result["score"],
        cost_usd=result["cost_usd"],
    )
    return result


@celery_app.task(
    bind=True,
    name="cv_evaluator.run",
    acks_late=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
)
def run(
    self: Task[Any, Any],
    run_id: str,
    empresa_id: str,
    vacante_id: str,
    candidato_id: str,
    cost_cap_usd: float = 0.05,
) -> CvEvaluatorResult:
    try:
        return asyncio.run(
            _run(
                run_id=run_id,
                empresa_id=empresa_id,
                vacante_id=vacante_id,
                candidato_id=candidato_id,
                cost_cap_usd=cost_cap_usd,
            ),
        )
    except Exception as exc:
        retries = self.request.retries or 0
        if is_transient_error(exc) and retries < (self.max_retries or 0):
            logger.warning(
                "cv_evaluator.run.retrying",
                run_id=run_id,
                attempt=retries + 1,
                error_type=type(exc).__name__,
            )
            raise self.retry(exc=exc, countdown=run_state.retry_countdown(retries)) from exc
        raise


# Re-export para que callers puedan capturar el cap exceeded.
__all__ = ["CostCapExceededError", "CvEvaluatorResult", "_run", "run"]
