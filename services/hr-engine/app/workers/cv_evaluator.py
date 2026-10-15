"""Tarea de cv-evaluator: traduce la petición y llama al caso de uso EvaluateCandidate.

La lógica está en `app/application`, el ciclo de vida del run en `ejecucion` y
los adaptadores en `app/infrastructure`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from celery import Task

from app.application.evaluate_candidate import EvaluateCandidate
from app.database import db_session
from app.domain.presupuesto import CostBudget
from app.infrastructure.evaluacion import LlmScoring, OpenAIEmbeddings, SqlCandidateRepository
from app.monitoring import logger
from app.security.tenant_context import set_tenant_context
from app.workers.celery_app import celery_app
from app.workers.ejecucion import correr_tarea, ejecutar_run

AGENT_SKILL = "cv-evaluator"


async def _run(
    *, run_id: str, empresa_id: str, vacante_id: str, candidato_id: str, cost_cap_usd: float = 0.05
) -> dict[str, Any]:
    async def evaluar(presupuesto: CostBudget) -> tuple[dict[str, Any], dict[str, Any]]:
        async with db_session() as db:
            await set_tenant_context(db, UUID(empresa_id), role="HR")
            caso = EvaluateCandidate(SqlCandidateRepository(db), OpenAIEmbeddings(), LlmScoring())
            r = await caso.ejecutar(
                vacante_id=UUID(vacante_id),
                candidato_id=UUID(candidato_id),
                presupuesto=presupuesto,
            )
            await db.commit()
        for cual in r.embeddings_aplazados:
            logger.warning("cv_evaluator.embedding_aplazado", cual=cual)
        fit = {"score": r.fit.score, "recommended_next_step": r.fit.siguiente_paso}
        guardado = {**fit, "application_id": str(r.application_id)}
        texto = {
            "rationale": r.fit.rationale,
            "gaps": list(r.fit.gaps),
            "strengths": list(r.fit.strengths),
        }
        return {**guardado, **texto}, {**guardado, "model": r.model}

    return await ejecutar_run(
        run_id=run_id,
        empresa_id=empresa_id,
        agent_skill=AGENT_SKILL,
        cost_cap_usd=cost_cap_usd,
        ids={"vacante_id": vacante_id, "candidato_id": candidato_id},
        trabajo=evaluar,
        del_payload=("score", "application_id", "recommended_next_step"),
        sin_guardar={"rationale": "", "gaps": [], "strengths": []},
    )


@celery_app.task(bind=True, name="cv_evaluator.run", acks_late=True, max_retries=3)
def run(
    self: Task[Any, Any],
    run_id: str,
    empresa_id: str,
    vacante_id: str,
    candidato_id: str,
    cost_cap_usd: float = 0.05,
    aplazamientos: int = 0,
) -> dict[str, Any]:
    ids = {"run_id": run_id, "empresa_id": empresa_id, "vacante_id": vacante_id}
    return correr_tarea(
        self,
        run_id=run_id,
        aplazamientos=aplazamientos,
        evento="cv_evaluator",
        trabajo=lambda: _run(**ids, candidato_id=candidato_id, cost_cap_usd=cost_cap_usd),
    )
