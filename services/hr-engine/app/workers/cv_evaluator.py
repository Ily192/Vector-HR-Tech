"""CV evaluator worker — evalúa un candidato↔vacante específico.

Diferencia vs sourcer:
- Sourcer: batch sobre N candidatos top-K vector.
- CV evaluator: single (candidato_id, vacante_id) — usado cuando un candidato
  aplica desde career-site (paso 1 del pipeline post-apply).

Pipeline:
  1. Lee candidato + vacante (ambas tienen que estar bajo el mismo tenant).
  2. Si la vacante no tiene embedding o el candidato no tiene cv_embedding,
     los genera.
  3. Score con Gemini Flash (mismo schema que sourcer).
  4. Upsert application status='evaluated'.

Output strict schema: `app.clients.scoring.CandidateFitResponse` que mirror-ea
`packages/types/src/hr.ts::CvEvaluationSchema`.
"""

from __future__ import annotations

import asyncio
from typing import TypedDict
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.embeddings import embed_text
from app.clients.scoring import score_candidate_fit
from app.database import db_session
from app.monitoring import logger
from app.repositories import hr as hr_repo
from app.security.tenant_context import set_tenant_context
from app.workers.celery_app import celery_app
from app.workers.cost_tracker import CostCapExceeded, CostTracker


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


async def _get_candidato_text(db: AsyncSession, candidato_id: UUID) -> tuple[str, str | None]:
    """Devuelve (texto_para_embedding, summary_para_scoring)."""
    row = (
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
    ).mappings().first()
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


async def _run(
    *,
    run_id: str,
    empresa_id: str,
    vacante_id: str,
    candidato_id: str,
    cost_cap_usd: float = 0.05,
) -> CvEvaluatorResult:
    log = logger.bind(
        run_id=run_id,
        empresa_id=empresa_id,
        agent_skill="cv-evaluator",
        vacante_id=vacante_id,
        candidato_id=candidato_id,
    )
    log.info("cv_evaluator.run.started")

    empresa_uuid = UUID(empresa_id)
    vacante_uuid = UUID(vacante_id)
    candidato_uuid = UUID(candidato_id)
    cost_tracker = CostTracker(cap_usd=cost_cap_usd)

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

        await hr_repo.update_run_status(
            db,
            run_id=run_id,
            status="completed",
            cost_usd=cost_tracker.spent_usd,
            payload={"score": scoring.response.score},
        )
        await db.commit()

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
    }
    log.info(
        "cv_evaluator.run.completed",
        score=result["score"],
        cost_usd=result["cost_usd"],
    )
    return result


@celery_app.task(name="cv_evaluator.run", acks_late=True, max_retries=3)
def run(
    run_id: str,
    empresa_id: str,
    vacante_id: str,
    candidato_id: str,
    cost_cap_usd: float = 0.05,
) -> CvEvaluatorResult:
    return asyncio.run(
        _run(
            run_id=run_id,
            empresa_id=empresa_id,
            vacante_id=vacante_id,
            candidato_id=candidato_id,
            cost_cap_usd=cost_cap_usd,
        ),
    )


# Re-export para que callers puedan capturar el cap exceeded.
__all__ = ["_run", "run", "CvEvaluatorResult", "CostCapExceeded"]
