"""Unit tests del cv_evaluator worker — monkeypatch de side-effects."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.clients.embeddings import EmbeddingResult
from app.clients.scoring import CandidateFitResponse, ScoringResult
from app.repositories import hr as hr_repo
from app.repositories import runs as runs_repo
from app.workers import cv_evaluator as cve_mod
from app.workers import run_state
from app.workers.cost_tracker import CostCapExceededError

EMPRESA_ID = "00000000-0000-0000-0000-000000000001"
VACANTE_ID = "00000000-0000-0000-0000-0000000000aa"
CANDIDATO_ID = "00000000-0000-0000-0000-0000000000bb"
RUN_ID = "00000000-0000-0000-0000-000000000020"


class _FakeDb:
    async def commit(self) -> None:
        return None

    async def execute(self, *_a: object, **_kw: object) -> Any:
        class _Result:
            def mappings(self) -> Any:
                return self

            def first(self) -> dict[str, str]:
                return {
                    "full_name": "Ana Dev",
                    "headline": "Senior Python",
                    "summary": "10 años con Python + Postgres + async",
                    "emb": "[0.1,0.2,0.3]",
                }

        return _Result()


@asynccontextmanager
async def _fake_db_session() -> AsyncIterator[_FakeDb]:
    yield _FakeDb()


def _run_row(
    run_id: str = RUN_ID,
    *,
    status: str = runs_repo.STATUS_PENDING,
    cost_usd: float = 0.0,
    payload: dict[str, Any] | None = None,
) -> runs_repo.RunRow:
    return runs_repo.RunRow(
        id=UUID(run_id),
        empresa_id=UUID(EMPRESA_ID),
        agent_skill="cv-evaluator",
        status=status,
        cost_usd=cost_usd,
        cost_cap_usd=0.05,
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
    async def fake_claim(**kwargs: Any) -> runs_repo.RunClaim:
        captured["claim"] = kwargs
        return runs_repo.RunClaim(outcome=outcome, run=run or _run_row(kwargs["run_id"]))

    async def fake_finish(**kwargs: Any) -> None:
        captured.setdefault("finish", []).append(kwargs)

    monkeypatch.setattr(run_state, "claim_run", fake_claim)
    monkeypatch.setattr(run_state, "finish_run", fake_finish)


@pytest.fixture
def patched(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {"upsert_args": None}

    async def fake_set_tenant_context(_db: object, _e: object, *, role: str = "HR") -> None:
        return None

    async def fake_get_vacante(_db: object, _id: object) -> hr_repo.VacanteRow:
        return hr_repo.VacanteRow(
            id=UUID(VACANTE_ID),
            empresa_id=UUID(EMPRESA_ID),
            title="Senior Python",
            jd="JD",
            icp_text="ICP Python LATAM",
            icp_embedding=[0.01] * 1536,
            status="open",
        )

    async def fake_update_vacante_embedding(_db: object, _id: object, _emb: object) -> None:
        return None

    async def fake_upsert(_db: object, **kw: Any) -> UUID:
        captured["upsert_args"] = kw
        return uuid4()

    async def fake_embed(_text: str, *, model: str | None = None) -> EmbeddingResult:
        return EmbeddingResult(
            vector=[0.0] * 1536,
            token_count=10,
            cost_usd=0.00001,
            model="text-embedding-3-small",
        )

    async def fake_score(_candidate: dict[str, Any], _icp: str) -> ScoringResult:
        return ScoringResult(
            response=CandidateFitResponse(
                score=8.5,
                rationale="Match fuerte en Python async y Postgres",
                gaps=["sin liderazgo de equipo"],
                strengths=["python", "sqlalchemy"],
                recommended_next_step="entrevista",
            ),
            input_tokens=200,
            output_tokens=80,
            cost_usd=0.0002,
            model="gemini-2.5-flash",
        )

    monkeypatch.setattr(cve_mod, "db_session", _fake_db_session)
    monkeypatch.setattr(cve_mod, "set_tenant_context", fake_set_tenant_context)
    monkeypatch.setattr(cve_mod, "embed_text", fake_embed)
    monkeypatch.setattr(cve_mod, "score_candidate_fit", fake_score)
    monkeypatch.setattr(hr_repo, "get_vacante", fake_get_vacante)
    monkeypatch.setattr(hr_repo, "update_vacante_embedding", fake_update_vacante_embedding)
    monkeypatch.setattr(hr_repo, "upsert_application", fake_upsert)
    _patch_run_state(monkeypatch, captured)
    return captured


@pytest.mark.asyncio
async def test_cv_evaluator_persists_and_returns_score(patched: dict[str, Any]) -> None:
    result = await cve_mod._run(
        run_id=RUN_ID,
        empresa_id=EMPRESA_ID,
        vacante_id=VACANTE_ID,
        candidato_id=CANDIDATO_ID,
        cost_cap_usd=0.05,
    )
    assert result["score"] == 8.5
    assert result["recommended_next_step"] == "entrevista"
    assert result["application_id"]
    assert result["deduplicated"] is False
    assert patched["upsert_args"]["fit_score"] == 8.5
    assert patched["upsert_args"]["fit_gaps"] == ["sin liderazgo de equipo"]

    finish = patched["finish"][-1]
    assert finish["status"] == runs_repo.STATUS_COMPLETED
    assert finish["cost_usd"] > 0
    assert finish["payload"]["score"] == 8.5


@pytest.mark.asyncio
async def test_claim_uses_cv_evaluator_skill(patched: dict[str, Any]) -> None:
    await cve_mod._run(
        run_id=RUN_ID,
        empresa_id=EMPRESA_ID,
        vacante_id=VACANTE_ID,
        candidato_id=CANDIDATO_ID,
    )
    assert patched["claim"]["agent_skill"] == "cv-evaluator"


@pytest.mark.asyncio
async def test_completed_run_is_not_reexecuted(
    monkeypatch: pytest.MonkeyPatch,
    patched: dict[str, Any],
) -> None:
    async def explode(*_a: object, **_kw: object) -> None:
        raise AssertionError("no debería llamarse a ningún LLM")

    monkeypatch.setattr(cve_mod, "embed_text", explode)
    monkeypatch.setattr(cve_mod, "score_candidate_fit", explode)
    _patch_run_state(
        monkeypatch,
        patched,
        outcome=runs_repo.ClaimOutcome.ALREADY_COMPLETED,
        run=_run_row(
            status=runs_repo.STATUS_COMPLETED,
            cost_usd=0.0003,
            payload={
                "score": 8.5,
                "application_id": "11111111-1111-1111-1111-111111111111",
                "recommended_next_step": "entrevista",
            },
        ),
    )

    result = await cve_mod._run(
        run_id=RUN_ID,
        empresa_id=EMPRESA_ID,
        vacante_id=VACANTE_ID,
        candidato_id=CANDIDATO_ID,
    )
    assert result["deduplicated"] is True
    assert result["score"] == 8.5
    assert result["cost_usd"] == 0.0003
    assert "finish" not in patched


@pytest.mark.asyncio
async def test_cost_cap_exceeded_marks_run_failed(
    monkeypatch: pytest.MonkeyPatch,
    patched: dict[str, Any],
) -> None:
    """CostCapExceededError ahora deja `status='failed'` + `error_message`."""

    async def vacante_sin_embedding(_db: object, _id: object) -> hr_repo.VacanteRow:
        return hr_repo.VacanteRow(
            id=UUID(VACANTE_ID),
            empresa_id=UUID(EMPRESA_ID),
            title="t",
            jd="jd",
            icp_text="icp",
            icp_embedding=None,
            status="open",
        )

    async def pricey_embed(_text: str, *, model: str | None = None) -> EmbeddingResult:
        return EmbeddingResult(
            vector=[0.0] * 1536,
            token_count=10,
            cost_usd=1.0,
            model="text-embedding-3-small",
        )

    monkeypatch.setattr(hr_repo, "get_vacante", vacante_sin_embedding)
    monkeypatch.setattr(cve_mod, "embed_text", pricey_embed)

    with pytest.raises(CostCapExceededError):
        await cve_mod._run(
            run_id=RUN_ID,
            empresa_id=EMPRESA_ID,
            vacante_id=VACANTE_ID,
            candidato_id=CANDIDATO_ID,
            cost_cap_usd=0.05,
        )

    finish = patched["finish"][-1]
    assert finish["status"] == runs_repo.STATUS_FAILED
    assert "CostCapExceededError" in finish["error_message"]
    assert finish["cost_usd"] == pytest.approx(1.0)
