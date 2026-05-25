"""Unit tests del cv_evaluator worker — monkeypatch de side-effects."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.clients.scoring import CandidateFitResponse, ScoringResult
from app.repositories import hr as hr_repo
from app.workers import cv_evaluator as cve_mod

EMPRESA_ID = "00000000-0000-0000-0000-000000000001"
VACANTE_ID = "00000000-0000-0000-0000-0000000000aa"
CANDIDATO_ID = "00000000-0000-0000-0000-0000000000bb"


class _FakeDb:
    async def commit(self) -> None:
        return None

    async def execute(self, *_a: object, **_kw: object) -> Any:
        class _Result:
            def mappings(self):
                return self

            def first(self):
                return {
                    "full_name": "Ana Dev",
                    "headline": "Senior Python",
                    "summary": "10 años con Python + Postgres + async",
                    "emb": "[0.1,0.2,0.3]",
                }

        return _Result()


@asynccontextmanager
async def _fake_db_session():
    yield _FakeDb()


@pytest.fixture
def patched(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {"upsert_args": None, "run_status": None}

    async def fake_set_tenant_context(_db, _e, *, role: str = "HR") -> None:  # noqa: ARG001
        return None

    async def fake_get_vacante(_db, _id):
        return hr_repo.VacanteRow(
            id=UUID(VACANTE_ID),
            empresa_id=UUID(EMPRESA_ID),
            title="Senior Python",
            jd="JD",
            icp_text="ICP Python LATAM",
            icp_embedding=[0.01] * 1536,
            status="open",
        )

    async def fake_update_vacante_embedding(_db, _id, _emb):
        return None

    async def fake_upsert(_db, **kw):
        captured["upsert_args"] = kw
        return uuid4()

    async def fake_update_run(_db, **kw):
        captured["run_status"] = kw
        return None

    async def fake_embed(_text: str, *, model: str | None = None):  # noqa: ARG001
        from app.clients.embeddings import EmbeddingResult

        return EmbeddingResult(
            vector=[0.0] * 1536,
            token_count=10,
            cost_usd=0.00001,
            model="text-embedding-3-small",
        )

    async def fake_score(_candidate: dict, _icp: str):
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
            model="gemini-1.5-flash",
        )

    monkeypatch.setattr(cve_mod, "db_session", _fake_db_session)
    monkeypatch.setattr(cve_mod, "set_tenant_context", fake_set_tenant_context)
    monkeypatch.setattr(cve_mod, "embed_text", fake_embed)
    monkeypatch.setattr(cve_mod, "score_candidate_fit", fake_score)
    monkeypatch.setattr(cve_mod.hr_repo, "get_vacante", fake_get_vacante)
    monkeypatch.setattr(cve_mod.hr_repo, "update_vacante_embedding", fake_update_vacante_embedding)
    monkeypatch.setattr(cve_mod.hr_repo, "upsert_application", fake_upsert)
    monkeypatch.setattr(cve_mod.hr_repo, "update_run_status", fake_update_run)
    return captured


@pytest.mark.asyncio
async def test_cv_evaluator_persists_and_returns_score(patched: dict[str, Any]) -> None:
    result = await cve_mod._run(
        run_id="00000000-0000-0000-0000-000000000020",
        empresa_id=EMPRESA_ID,
        vacante_id=VACANTE_ID,
        candidato_id=CANDIDATO_ID,
        cost_cap_usd=0.05,
    )
    assert result["score"] == 8.5
    assert result["recommended_next_step"] == "entrevista"
    assert result["application_id"]
    assert patched["upsert_args"]["fit_score"] == 8.5
    assert patched["upsert_args"]["fit_gaps"] == ["sin liderazgo de equipo"]
    assert patched["run_status"]["status"] == "completed"
