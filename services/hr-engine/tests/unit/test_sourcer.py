"""Unit tests para el sourcer worker — sin DB ni Celery ni LLMs reales.

Estrategia: monkeypatch de las funciones de side-effect (embed_text,
score_candidate_fit, db_session, set_tenant_context, hr_repo.*, run_state.*)
para que `_run` corra deterministicamente.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.clients.embeddings import EmbeddingResult
from app.clients.scoring import CandidateFitResponse, ScoringResult
from app.repositories import hr as hr_repo
from app.repositories import runs as runs_repo
from app.workers import run_state
from app.workers import sourcer as sourcer_mod

EMPRESA_ID = "00000000-0000-0000-0000-000000000001"
VACANTE_ID = "00000000-0000-0000-0000-0000000000aa"


@dataclass
class _FakeDb:
    """Sustituto del AsyncSession — solo necesita commit() y los métodos que
    los repositories llamen. Como reemplazamos los repos completos, alcanza con
    commit no-op + tracking de llamadas."""

    committed: bool = False

    async def commit(self) -> None:
        self.committed = True

    async def execute(self, *_a: object, **_kw: object) -> None:
        return None


@asynccontextmanager
async def _fake_db_session() -> AsyncIterator[_FakeDb]:
    yield _FakeDb()


def _make_embedding_result(cost: float = 0.0001) -> EmbeddingResult:
    return EmbeddingResult(
        vector=[0.01] * 1536,
        token_count=200,
        cost_usd=cost,
        model="text-embedding-3-small",
    )


def _make_scoring_result(score: float, name: str = "x") -> ScoringResult:
    return ScoringResult(
        response=CandidateFitResponse(
            score=score,
            rationale=f"rationale for {name} con detalle suficiente",
            gaps=["sin liderazgo"],
            strengths=["python", "sql"],
            recommended_next_step="psicometrico",
        ),
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.0001,
        model="gemini-2.5-flash",
    )


def _run_row(
    run_id: str,
    *,
    status: str = runs_repo.STATUS_PENDING,
    cost_usd: float = 0.0,
    cost_cap_usd: float | None = 0.05,
    payload: dict[str, Any] | None = None,
) -> runs_repo.RunRow:
    return runs_repo.RunRow(
        id=UUID(run_id),
        empresa_id=UUID(EMPRESA_ID),
        agent_skill="sourcer",
        status=status,
        cost_usd=cost_usd,
        cost_cap_usd=cost_cap_usd,
        error_message=None,
        payload=payload,
    )


def _patch_run_state(
    monkeypatch: pytest.MonkeyPatch,
    captured: dict[str, Any],
    *,
    outcome: runs_repo.ClaimOutcome = runs_repo.ClaimOutcome.CLAIMED,
    run: runs_repo.RunRow | None = None,
) -> None:
    async def fake_claim(
        *,
        run_id: str,
        empresa_id: Any,
        agent_skill: str,
        cost_cap_usd: float,
    ) -> runs_repo.RunClaim:
        captured["claim"] = {
            "run_id": run_id,
            "empresa_id": str(empresa_id),
            "agent_skill": agent_skill,
            "cost_cap_usd": cost_cap_usd,
        }
        return runs_repo.RunClaim(outcome=outcome, run=run or _run_row(run_id))

    async def fake_finish(**kwargs: Any) -> None:
        captured.setdefault("finish", []).append(kwargs)

    monkeypatch.setattr(run_state, "claim_run", fake_claim)
    monkeypatch.setattr(run_state, "finish_run", fake_finish)


@pytest.fixture
def patched_world(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Reemplaza DB + LLMs + estado de runs por fakes."""
    captured: dict[str, Any] = {"upserts": []}

    async def fake_embed(text: str, *, model: str | None = None) -> EmbeddingResult:
        return _make_embedding_result()

    async def fake_score(candidate: dict[str, Any], icp_text: str) -> ScoringResult:
        return _make_scoring_result(7.5, candidate.get("full_name", "x"))

    async def fake_get_vacante(_db: object, _id: object) -> hr_repo.VacanteRow:
        return hr_repo.VacanteRow(
            id=UUID(VACANTE_ID),
            empresa_id=UUID(EMPRESA_ID),
            title="Senior Python",
            jd="JD largo",
            icp_text="Senior Python LATAM remoto",
            icp_embedding=[0.02] * 1536,
            status="open",
        )

    async def fake_match(
        _db: object,
        _emb: object,
        *,
        limit: int = 50,
    ) -> list[hr_repo.CandidatoMatch]:
        return [
            hr_repo.CandidatoMatch(
                id=uuid4(),
                full_name=f"Cand {i}",
                headline="HL",
                summary="S",
                distance=0.1,
            )
            for i in range(min(limit, 3))
        ]

    async def fake_upsert(_db: object, **kw: Any) -> UUID:
        captured["upserts"].append(kw)
        return uuid4()

    async def fake_update_vacante_embedding(_db: object, _id: object, _emb: object) -> None:
        return None

    async def fake_set_tenant_context(_db: object, _e: object, *, role: str = "HR") -> None:
        return None

    monkeypatch.setattr(sourcer_mod, "db_session", _fake_db_session)
    monkeypatch.setattr(sourcer_mod, "set_tenant_context", fake_set_tenant_context)
    monkeypatch.setattr(sourcer_mod, "embed_text", fake_embed)
    monkeypatch.setattr(sourcer_mod, "score_candidate_fit", fake_score)
    monkeypatch.setattr(hr_repo, "get_vacante", fake_get_vacante)
    monkeypatch.setattr(hr_repo, "match_candidates", fake_match)
    monkeypatch.setattr(hr_repo, "upsert_application", fake_upsert)
    monkeypatch.setattr(hr_repo, "update_vacante_embedding", fake_update_vacante_embedding)
    _patch_run_state(monkeypatch, captured)
    return captured


@pytest.mark.asyncio
async def test_run_with_vacante_id_persists_applications(
    patched_world: dict[str, Any],
) -> None:
    result = await sourcer_mod._run(
        run_id="00000000-0000-0000-0000-000000000010",
        empresa_id=EMPRESA_ID,
        vacante_id=VACANTE_ID,
        target=5,
        cost_cap_usd=0.05,
    )
    assert result["candidates_found"] == 3
    assert result["vacante_id"] == VACANTE_ID
    assert result["deduplicated"] is False
    assert all(c["application_id"] is not None for c in result["candidates"])
    assert len(patched_world["upserts"]) == 3
    assert result["capped"] is False

    # El estado del run se persiste de verdad (antes era un UPDATE a 0 filas).
    finish = patched_world["finish"][-1]
    assert finish["status"] == runs_repo.STATUS_COMPLETED
    assert finish["payload"] == {"candidates_found": 3, "capped": False}
    assert finish["cost_usd"] > 0


@pytest.mark.asyncio
async def test_run_with_icp_text_only_does_not_persist(patched_world: dict[str, Any]) -> None:
    result = await sourcer_mod._run(
        run_id="00000000-0000-0000-0000-000000000011",
        empresa_id=EMPRESA_ID,
        icp_text="HRBP senior LATAM con dominio en hiring tech",
        target=5,
        cost_cap_usd=0.05,
    )
    assert result["vacante_id"] is None
    assert result["candidates_found"] == 3
    assert len(patched_world["upserts"]) == 0


@pytest.mark.asyncio
async def test_run_claims_with_agent_skill_and_tenant(patched_world: dict[str, Any]) -> None:
    await sourcer_mod._run(
        run_id="00000000-0000-0000-0000-000000000015",
        empresa_id=EMPRESA_ID,
        icp_text="ICP",
        cost_cap_usd=0.05,
    )
    assert patched_world["claim"] == {
        "run_id": "00000000-0000-0000-0000-000000000015",
        "empresa_id": EMPRESA_ID,
        "agent_skill": "sourcer",
        "cost_cap_usd": 0.05,
    }


@pytest.mark.asyncio
async def test_completed_run_is_not_reexecuted(
    monkeypatch: pytest.MonkeyPatch,
    patched_world: dict[str, Any],
) -> None:
    """Idempotencia: con acks_late el broker re-entrega; no re-gastamos LLM."""
    run_id = "00000000-0000-0000-0000-000000000016"

    async def explode(*_a: object, **_kw: object) -> None:
        raise AssertionError("no debería llamarse a ningún LLM")

    monkeypatch.setattr(sourcer_mod, "embed_text", explode)
    monkeypatch.setattr(sourcer_mod, "score_candidate_fit", explode)
    _patch_run_state(
        monkeypatch,
        patched_world,
        outcome=runs_repo.ClaimOutcome.ALREADY_COMPLETED,
        run=_run_row(
            run_id,
            status=runs_repo.STATUS_COMPLETED,
            cost_usd=0.0042,
            payload={"candidates_found": 7, "capped": True},
        ),
    )

    result = await sourcer_mod._run(
        run_id=run_id,
        empresa_id=EMPRESA_ID,
        icp_text="ICP",
        cost_cap_usd=0.05,
    )
    assert result["deduplicated"] is True
    assert result["candidates_found"] == 7
    assert result["cost_usd"] == 0.0042
    assert result["capped"] is True
    assert "finish" not in patched_world


@pytest.mark.asyncio
async def test_run_in_progress_elsewhere_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
    patched_world: dict[str, Any],
) -> None:
    run_id = "00000000-0000-0000-0000-000000000017"
    _patch_run_state(
        monkeypatch,
        patched_world,
        outcome=runs_repo.ClaimOutcome.IN_PROGRESS,
        run=_run_row(run_id, status=runs_repo.STATUS_RUNNING),
    )
    result = await sourcer_mod._run(
        run_id=run_id,
        empresa_id=EMPRESA_ID,
        icp_text="ICP",
        cost_cap_usd=0.05,
    )
    assert result["deduplicated"] is True
    assert result["candidates"] == []


@pytest.mark.asyncio
async def test_run_respects_cost_cap(
    monkeypatch: pytest.MonkeyPatch,
    patched_world: dict[str, Any],
) -> None:
    """Si el cap es muy bajo, el sourcer corta antes y marca capped=True."""

    async def expensive_score(candidate: dict[str, Any], icp_text: str) -> ScoringResult:
        result = _make_scoring_result(6.0)
        return ScoringResult(
            response=result.response,
            input_tokens=100,
            output_tokens=50,
            cost_usd=10.0,
            model="gemini-2.5-flash",
        )

    async def fake_embed(_text: str, *, model: str | None = None) -> EmbeddingResult:
        # Embedding también caro para que cape antes del primer scoring.
        return _make_embedding_result(cost=0.05)

    monkeypatch.setattr(sourcer_mod, "embed_text", fake_embed)
    monkeypatch.setattr(sourcer_mod, "score_candidate_fit", expensive_score)

    result = await sourcer_mod._run(
        run_id="00000000-0000-0000-0000-000000000012",
        empresa_id=EMPRESA_ID,
        icp_text="ICP cualquiera",
        target=10,
        cost_cap_usd=0.001,
    )
    assert result["capped"] is True
    assert result["candidates_found"] == 0


@pytest.mark.asyncio
async def test_failure_persists_failed_status_with_message(
    monkeypatch: pytest.MonkeyPatch,
    patched_world: dict[str, Any],
) -> None:
    """`error_message` existía y jamás se le pasaba nada. Ahora sí."""

    async def boom(_db: object, _id: object) -> hr_repo.VacanteRow:
        raise RuntimeError("pgvector se cayó")

    monkeypatch.setattr(hr_repo, "get_vacante", boom)

    with pytest.raises(RuntimeError, match="pgvector"):
        await sourcer_mod._run(
            run_id="00000000-0000-0000-0000-000000000018",
            empresa_id=EMPRESA_ID,
            vacante_id=VACANTE_ID,
            cost_cap_usd=0.05,
        )

    finish = patched_world["finish"][-1]
    assert finish["status"] == runs_repo.STATUS_FAILED
    assert "pgvector se cayó" in finish["error_message"]
    assert finish["error_message"].startswith("RuntimeError")


@pytest.mark.asyncio
async def test_expensive_embedding_caps_before_scoring(
    monkeypatch: pytest.MonkeyPatch,
    patched_world: dict[str, Any],
) -> None:
    async def pricey_embed(_text: str, *, model: str | None = None) -> EmbeddingResult:
        return _make_embedding_result(cost=1.0)

    async def fake_get_vacante_sin_embedding(_db: object, _id: object) -> hr_repo.VacanteRow:
        return hr_repo.VacanteRow(
            id=UUID(VACANTE_ID),
            empresa_id=UUID(EMPRESA_ID),
            title="t",
            jd="jd",
            icp_text="icp",
            icp_embedding=None,
            status="open",
        )

    monkeypatch.setattr(sourcer_mod, "embed_text", pricey_embed)
    monkeypatch.setattr(hr_repo, "get_vacante", fake_get_vacante_sin_embedding)

    # El embedding gasta 1.0 (>> cap): el assert previo a cada scoring corta.
    async def fake_match(
        _db: object,
        _emb: object,
        *,
        limit: int = 50,
    ) -> list[hr_repo.CandidatoMatch]:
        return [
            hr_repo.CandidatoMatch(
                id=uuid4(),
                full_name="C",
                headline=None,
                summary=None,
                distance=0.1,
            ),
        ]

    monkeypatch.setattr(hr_repo, "match_candidates", fake_match)

    result = await sourcer_mod._run(
        run_id="00000000-0000-0000-0000-000000000019",
        empresa_id=EMPRESA_ID,
        vacante_id=VACANTE_ID,
        cost_cap_usd=0.05,
    )
    assert result["capped"] is True


@pytest.mark.asyncio
async def test_run_rejects_invalid_empresa_id() -> None:
    with pytest.raises(ValueError, match="empresa_id"):
        await sourcer_mod._run(
            run_id="00000000-0000-0000-0000-000000000013",
            empresa_id="not-a-uuid",
            icp_text="x",
        )


@pytest.mark.asyncio
async def test_run_requires_vacante_or_icp_text(patched_world: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="requerido"):
        await sourcer_mod._run(
            run_id="00000000-0000-0000-0000-000000000014",
            empresa_id=EMPRESA_ID,
        )
    assert patched_world["finish"][-1]["status"] == runs_repo.STATUS_FAILED


# ── Wrapper Celery: reintentos reales ───────────────────────────────────────


def _call_task_as_worker(**kwargs: Any) -> Any:
    """Invoca la task como lo haría un worker (no `called_directly`).

    `is_eager=True` evita que `self.retry()` intente re-encolar contra Redis:
    en ese modo Celery levanta `Retry` en vez de hablar con el broker.
    """
    sourcer_mod.run.push_request(called_directly=False, retries=0, is_eager=True)
    try:
        return sourcer_mod.run(**kwargs)
    finally:
        sourcer_mod.run.pop_request()


def test_celery_wrapper_retries_transient_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """`max_retries=3` sin `bind=True`/`self.retry()` no reintentaba NADA."""
    import httpx
    import openai
    from celery.exceptions import Retry

    async def transient(**_kw: Any) -> None:
        raise openai.APITimeoutError(request=httpx.Request("POST", "https://api.openai.com"))

    monkeypatch.setattr(sourcer_mod, "_run", transient)
    with pytest.raises(Retry):
        _call_task_as_worker(run_id="r", empresa_id=EMPRESA_ID, icp_text="x")


def test_celery_wrapper_does_not_retry_business_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un cost cap excedido o un UUID inválido no mejoran reintentando."""
    from celery.exceptions import Retry

    async def permanent(**_kw: Any) -> None:
        raise ValueError("empresa_id no es un UUID válido")

    monkeypatch.setattr(sourcer_mod, "_run", permanent)
    with pytest.raises(ValueError, match="UUID"):
        _call_task_as_worker(run_id="r", empresa_id=EMPRESA_ID, icp_text="x")
    assert Retry is not None


def test_celery_wrapper_stops_retrying_after_max_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx
    import openai

    async def transient(**_kw: Any) -> None:
        raise openai.APITimeoutError(request=httpx.Request("POST", "https://api.openai.com"))

    monkeypatch.setattr(sourcer_mod, "_run", transient)
    sourcer_mod.run.push_request(called_directly=False, retries=3, is_eager=True)
    try:
        with pytest.raises(openai.APITimeoutError):
            sourcer_mod.run(run_id="r", empresa_id=EMPRESA_ID, icp_text="x")
    finally:
        sourcer_mod.run.pop_request()


def test_celery_task_config_has_timeouts_and_limits() -> None:
    conf = sourcer_mod.celery_app.conf
    assert conf.task_time_limit > 0
    assert conf.task_soft_time_limit < conf.task_time_limit
    assert conf.result_expires > 0
    assert conf.broker_transport_options["visibility_timeout"] > conf.task_time_limit
    assert conf.task_default_rate_limit
    assert sourcer_mod.run.max_retries == 3
