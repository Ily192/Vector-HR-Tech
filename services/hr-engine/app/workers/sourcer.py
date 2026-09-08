"""Sourcer worker — busca y rankea candidatos según el ICP de la vacante.

Pipeline:
  1. Toma el lock del run (`runs`) — idempotencia ante redelivery.
  2. Lee vacante por id (o usa `icp_text` directo si se invoca sin vacante).
  3. Si vacante.icp_embedding es null → genera con OpenAI text-embedding-3-small
     y la persiste.
  4. Vector match en pgvector contra `candidatos.cv_embedding` (HNSW cosine).
  5. Scoring per candidato con Gemini Flash (structured JSON output).
  6. Upsert en `applications` con fit_score / rationale / gaps.
  7. Track costo contra el cost_cap del run-token y lo persiste en `runs`.

Patrón Vortex (heredado de SDR-prospection):
  - `async def _run(...)` testeable — los side-effects son funciones importadas,
    los tests las monkeypatchean.
  - `@celery_app.task` wrapper hace `asyncio.run(_run(...))` y decide retry.

Idempotencia (ADR: `task_acks_late=True` + `task_reject_on_worker_lost=True`
garantizan redelivery): la fila `runs` es el lock. Un run ya `completed` no
vuelve a ejecutar NI UNA llamada a LLM.

RLS multi-tenant (ADR-004): `set_tenant_context` setea `request.jwt.claim.empresa_id`
en la sesión Postgres antes de cualquier query del dominio.
"""

from __future__ import annotations

import asyncio
from typing import Any, TypedDict
from uuid import UUID

from celery import Task

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

AGENT_SKILL = "sourcer"


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
    deduplicated: bool


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
        except CostCapExceededError as exc:
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


def _deduplicated_result(
    *,
    run_id: str,
    empresa_id: UUID,
    vacante_id: UUID | None,
    run: runs_repo.RunRow,
) -> SourcerResult:
    """Resultado slim para un run ya ejecutado.

    No re-materializamos los candidatos (viven en `applications`) para no
    duplicar PII en el result backend.
    """
    payload = run.payload or {}
    return {
        "run_id": run_id,
        "empresa_id": str(empresa_id),
        "vacante_id": str(vacante_id) if vacante_id else None,
        "candidates_found": int(payload.get("candidates_found", 0)),
        "candidates": [],
        "cost_usd": round(run.cost_usd, 6),
        "cost_breakdown": {},
        "capped": bool(payload.get("capped", False)),
        "deduplicated": True,
    }


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
    bind_log_context(run_id=run_id, empresa_id=empresa_id, agent_skill=AGENT_SKILL)
    log = logger.bind(
        run_id=run_id,
        empresa_id=empresa_id,
        agent_skill=AGENT_SKILL,
        vacante_id=vacante_id,
        target=target,
        sources=sources,
    )
    log.info("sourcer.run.started")

    empresa_uuid = _validate_uuid(empresa_id, "empresa_id")
    if empresa_uuid is None:
        raise ValueError("empresa_id es requerido")
    vacante_uuid = _validate_uuid(vacante_id, "vacante_id")

    claim = await run_state.claim_run(
        run_id=run_id,
        empresa_id=empresa_uuid,
        agent_skill=AGENT_SKILL,
        cost_cap_usd=cost_cap_usd,
    )
    if claim.outcome is not runs_repo.ClaimOutcome.CLAIMED:
        log.warning("sourcer.run.skipped", outcome=str(claim.outcome))
        clear_log_context()
        return _deduplicated_result(
            run_id=run_id,
            empresa_id=empresa_uuid,
            vacante_id=vacante_uuid,
            run=claim.run,
        )

    # El cap efectivo nunca supera el que quedó grabado al encolar.
    effective_cap = min(cost_cap_usd, claim.run.cost_cap_usd or cost_cap_usd)
    cost_tracker = CostTracker(cap_usd=effective_cap)

    try:
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
                db,
                icp_embedding,
                limit=max(target * 3, 10),
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

            await db.commit()

        await run_state.finish_run(
            run_id=run_id,
            status=runs_repo.STATUS_COMPLETED,
            cost_usd=cost_tracker.spent_usd,
            payload={"candidates_found": len(top), "capped": capped},
        )
    except Exception as exc:
        # El cost cap excedido (o cualquier otra excepción) ahora deja rastro:
        # antes `error_message` existía y nunca se le pasaba nada.
        log.error(
            "sourcer.run.failed",
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

    result: SourcerResult = {
        "run_id": run_id,
        "empresa_id": str(empresa_uuid),
        "vacante_id": str(vacante_uuid) if vacante_uuid else None,
        "candidates_found": len(top),
        "candidates": top,
        "cost_usd": round(cost_tracker.spent_usd, 6),
        "cost_breakdown": {k: round(v, 6) for k, v in cost_tracker.breakdown.items()},
        "capped": capped,
        "deduplicated": False,
    }
    log.info(
        "sourcer.run.completed",
        candidates_found=result["candidates_found"],
        cost_usd=result["cost_usd"],
        capped=result["capped"],
    )
    return result


@celery_app.task(
    bind=True,
    name="sourcer.run",
    acks_late=True,
    max_retries=3,
    # `max_retries` solo no reintenta nada: hace falta `bind=True` + `self.retry()`
    # (o `autoretry_for`). Acá reintentamos SOLO errores transitorios: un
    # CostCapExceededError o un UUID inválido no mejoran reintentando.
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
)
def run(
    self: Task[Any, Any],
    run_id: str,
    empresa_id: str,
    vacante_id: str | None = None,
    icp_text: str | None = None,
    target: int = 50,
    sources: list[str] | None = None,
    cost_cap_usd: float = 0.05,
) -> SourcerResult:
    """Celery wrapper. Llama `_run` async y devuelve dict JSON-serializable."""
    try:
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
    except Exception as exc:
        retries = self.request.retries or 0
        if is_transient_error(exc) and retries < (self.max_retries or 0):
            logger.warning(
                "sourcer.run.retrying",
                run_id=run_id,
                attempt=retries + 1,
                error_type=type(exc).__name__,
            )
            raise self.retry(exc=exc, countdown=run_state.retry_countdown(retries)) from exc
        raise
