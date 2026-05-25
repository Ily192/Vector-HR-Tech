"""Sourcer worker — busca y rankea candidatos según el ICP de la vacante.

Pipeline:
  1. Lee vacante por id (o usa `icp_text` directo si se invoca sin vacante).
  2. Si vacante.icp_embedding es null → genera con OpenAI text-embedding-3-small
     y la persiste.
  3. Vector match en pgvector contra `candidatos.cv_embedding` (HNSW cosine).
  4. Scoring per candidato con Gemini 1.5 Flash (structured JSON output).
  5. Upsert en `applications` con fit_score / rationale / gaps.
  6. Track costo contra el cost_cap del run-token.

Patrón Vortex (heredado de SDR-prospection):
  - `async def _run(...)` testeable — los side-effects son funciones importadas,
    los tests las monkeypatchean.
  - `@celery_app.task` wrapper hace `asyncio.run(_run(...))`.

RLS multi-tenant (ADR-004): `set_tenant_context` setea `request.jwt.claim.empresa_id`
en la sesión Postgres antes de cualquier query del dominio.
"""

from __future__ import annotations

import asyncio
from typing import Any, TypedDict
from uuid import UUID

from app.clients.embeddings import embed_text
from app.clients.scoring import score_candidate_fit
from app.database import db_session
from app.monitoring import logger
from app.repositories import hr as hr_repo
from app.security.tenant_context import set_tenant_context
from app.workers.celery_app import celery_app
from app.workers.cost_tracker import CostCapExceeded, CostTracker


class CandidateResult(TypedDict):
    candidato_id: str
    full_name: str
    score: float
    rationale: str
    gaps: list[str]
    strengths: list[str]
    recommended_next_step: str
    application_id: str | None


class SourcerResult(TypedDict):
    run_id: str
    empresa_id: str
    vacante_id: str | None
    candidates_found: int
    candidates: list[CandidateResult]
    cost_usd: float
    cost_breakdown: dict[str, float]
    capped: bool


def _validate_uuid(value: str | None, name: str) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValueError(f"{name} no es un UUID válido: {value}") from exc


async def _resolve_icp(
    db: Any,
    *,
    vacante_id: UUID | None,
    icp_text: str | None,
    cost_tracker: CostTracker,
) -> tuple[list[float], str]:
    """Devuelve (embedding, icp_text) listos para el match.

    Si hay vacante, la usa como source-of-truth y genera embedding si falta.
    Si no, embebe el icp_text suelto (modo ad-hoc).
    """
    if vacante_id:
        vacante = await hr_repo.get_vacante(db, vacante_id)
        if vacante is None:
            raise ValueError(f"vacante {vacante_id} no existe (o RLS la oculta)")
        icp_source = vacante.icp_text or vacante.jd
        if vacante.icp_embedding:
            return vacante.icp_embedding, icp_source
        cost_tracker.assert_under_cap()
        emb = await embed_text(icp_source)
        cost_tracker.add(emb.cost_usd, "embedding_icp")
        await hr_repo.update_vacante_embedding(db, vacante_id, emb.vector)
        return emb.vector, icp_source

    if not icp_text:
        raise ValueError("vacante_id o icp_text es requerido")
    cost_tracker.assert_under_cap()
    emb = await embed_text(icp_text)
    cost_tracker.add(emb.cost_usd, "embedding_icp")
    return emb.vector, icp_text


async def _score_candidates(
    candidates: list[hr_repo.CandidatoMatch],
    icp_text: str,
    cost_tracker: CostTracker,
) -> tuple[list[CandidateResult], bool]:
    """Llama Gemini por candidato. Cortocircuita si se excede cost cap.

    Devuelve (scored, capped) — `capped=True` significa que paramos por cost cap
    antes de procesar todos los candidatos.
    """
    scored: list[CandidateResult] = []
    capped = False
    for cand in candidates:
        try:
            cost_tracker.assert_under_cap()
        except CostCapExceeded as exc:
            logger.warning(
                "sourcer.cost_cap_reached",
                processed=len(scored),
                pending=len(candidates) - len(scored),
                reason=str(exc),
            )
            capped = True
            break
        scoring = await score_candidate_fit(
            {
                "full_name": cand.full_name,
                "headline": cand.headline,
                "summary": cand.summary,
            },
            icp_text,
        )
        cost_tracker.add(scoring.cost_usd, "scoring")
        scored.append(
            {
                "candidato_id": str(cand.id),
                "full_name": cand.full_name,
                "score": scoring.response.score,
                "rationale": scoring.response.rationale,
                "gaps": list(scoring.response.gaps),
                "strengths": list(scoring.response.strengths),
                "recommended_next_step": scoring.response.recommended_next_step,
                "application_id": None,
            },
        )
    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored, capped


async def _run(
    *,
    run_id: str,
    empresa_id: str,
    vacante_id: str | None = None,
    icp_text: str | None = None,
    target: int = 50,
    sources: list[str] | None = None,
    cost_cap_usd: float = 0.05,
) -> SourcerResult:
    """Orquestación pura — testeable monkey-patcheando las funciones importadas."""
    sources = sources or ["internal"]
    log = logger.bind(
        run_id=run_id,
        empresa_id=empresa_id,
        agent_skill="sourcer",
        vacante_id=vacante_id,
        target=target,
        sources=sources,
    )
    log.info("sourcer.run.started")

    empresa_uuid = _validate_uuid(empresa_id, "empresa_id")
    if empresa_uuid is None:
        raise ValueError("empresa_id es requerido")
    vacante_uuid = _validate_uuid(vacante_id, "vacante_id")

    cost_tracker = CostTracker(cap_usd=cost_cap_usd)
    capped = False

    async with db_session() as db:
        await set_tenant_context(db, empresa_uuid, role="HR")

        icp_embedding, icp_resolved = await _resolve_icp(
            db,
            vacante_id=vacante_uuid,
            icp_text=icp_text,
            cost_tracker=cost_tracker,
        )

        # Pull un buffer (3x target) para que el scoring tenga de dónde elegir.
        matches = await hr_repo.match_candidates(
            db, icp_embedding, limit=max(target * 3, 10),
        )
        log.info("sourcer.vector_matched", count=len(matches))

        scored, capped = await _score_candidates(matches, icp_resolved, cost_tracker)

        top = scored[:target]

        if vacante_uuid:
            for c in top:
                application_id = await hr_repo.upsert_application(
                    db,
                    empresa_id=empresa_uuid,
                    vacante_id=vacante_uuid,
                    candidato_id=c["candidato_id"],
                    fit_score=c["score"],
                    fit_rationale=c["rationale"],
                    fit_gaps=c["gaps"],
                )
                c["application_id"] = str(application_id)

        await hr_repo.update_run_status(
            db,
            run_id=run_id,
            status="completed",
            cost_usd=cost_tracker.spent_usd,
            payload={"candidates_found": len(top), "capped": capped},
        )

        await db.commit()

    result: SourcerResult = {
        "run_id": run_id,
        "empresa_id": str(empresa_uuid),
        "vacante_id": str(vacante_uuid) if vacante_uuid else None,
        "candidates_found": len(top),
        "candidates": top,
        "cost_usd": round(cost_tracker.spent_usd, 6),
        "cost_breakdown": {k: round(v, 6) for k, v in cost_tracker.breakdown.items()},
        "capped": capped,
    }
    log.info(
        "sourcer.run.completed",
        candidates_found=result["candidates_found"],
        cost_usd=result["cost_usd"],
        capped=result["capped"],
    )
    return result


@celery_app.task(name="sourcer.run", acks_late=True, max_retries=3)
def run(
    run_id: str,
    empresa_id: str,
    vacante_id: str | None = None,
    icp_text: str | None = None,
    target: int = 50,
    sources: list[str] | None = None,
    cost_cap_usd: float = 0.05,
) -> SourcerResult:
    """Celery wrapper. Llama `_run` async y devuelve dict JSON-serializable."""
    return asyncio.run(
        _run(
            run_id=run_id,
            empresa_id=empresa_id,
            vacante_id=vacante_id,
            icp_text=icp_text,
            target=target,
            sources=sources,
            cost_cap_usd=cost_cap_usd,
        ),
    )
