"""Unit tests para el sourcer worker — sin DB ni Celery ni LLMs reales.

Estrategia: monkeypatch de las funciones de side-effect (embed_text,
score_candidate_fit, db_session, set_tenant_context, hr_repo.*) para que `_run`
corra deterministicamente.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.clients.scoring import CandidateFitResponse
from app.repositories import hr as hr_repo
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
async def _fake_db_session():
    yield _FakeDb()


def _make_embedding_result(cost: float = 0.0001):
    from app.clients.embeddings import EmbeddingResult

    return EmbeddingResult(
        vector=[0.01] * 1536,
        token_count=200,
        cost_usd=cost,
        model="text-embedding-3-small",
    )


def _make_scoring_result(score: float, name: str = "x"):
    from app.clients.scoring import ScoringResult

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
        model="gemini-1.5-flash",
    )


@pytest.fixture
def patched_world(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Reemplaza DB + LLMs por fakes. Devuelve handle para customizar."""
    captured_upserts: list[dict[str, Any]] = []

    async def fake_embed(text: str, *, model: str | None = None):  # noqa: ARG001
        return _make_embedding_result()

    async def fake_score(candidate: dict, icp_text: str):  # noqa: ARG001
        return _make_scoring_result(7.5, candidate.get("full_name", "x"))

    async def fake_get_vacante(_db, _id):
        return hr_repo.VacanteRow(
            id=UUID(VACANTE_ID),
            empresa_id=UUID(EMPRESA_ID),
            title="Senior Python",
            jd="JD largo",
            icp_text="Senior Python LATAM remoto",
            icp_embedding=[0.02] * 1536,
            status="open",
        )

    async def fake_match(_db, _emb, *, limit: int = 50):
        return [
            hr_repo.CandidatoMatch(
                id=uuid4(), full_name=f"Cand {i}", headline="HL", summary="S", distance=0.1,
            )
            for i in range(min(limit, 3))
        ]

    async def fake_upsert(_db, **kw):
        captured_upserts.append(kw)
        return uuid4()

    async def fake_update_run(_db, **_kw):
        return None

    async def fake_update_vacante_embedding(_db, _id, _emb):
        return None

    async def fake_set_tenant_context(_db, _empresa_id, *, role: str = "HR") -> None:  # noqa: ARG001
        return None

    monkeypatch.setattr(sourcer_mod, "db_session", _fake_db_session)
    monkeypatch.setattr(sourcer_mod, "set_tenant_context", fake_set_tenant_context)
    monkeypatch.setattr(sourcer_mod, "embed_text", fake_embed)
    monkeypatch.setattr(sourcer_mod, "score_candidate_fit", fake_score)
    monkeypatch.setattr(hr_repo, "get_vacante", fake_get_vacante)
    monkeypatch.setattr(hr_repo, "match_candidates", fake_match)
    monkeypatch.setattr(hr_repo, "upsert_application", fake_upsert)
    monkeypatch.setattr(hr_repo, "update_run_status", fake_update_run)
    monkeypatch.setattr(hr_repo, "update_vacante_embedding", fake_update_vacante_embedding)
    # También en el módulo sourcer porque se importa como `from app.repositories import hr as hr_repo`
    monkeypatch.setattr(sourcer_mod.hr_repo, "get_vacante", fake_get_vacante)
    monkeypatch.setattr(sourcer_mod.hr_repo, "match_candidates", fake_match)
    monkeypatch.setattr(sourcer_mod.hr_repo, "upsert_application", fake_upsert)
    monkeypatch.setattr(sourcer_mod.hr_repo, "update_run_status", fake_update_run)
    monkeypatch.setattr(
        sourcer_mod.hr_repo, "update_vacante_embedding", fake_update_vacante_embedding,
    )

    return {"upserts": captured_upserts}


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
    assert all(c["application_id"] is not None for c in result["candidates"])
    assert len(patched_world["upserts"]) == 3
    assert result["capped"] is False


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
async def test_run_respects_cost_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si el cap es muy bajo, el sourcer corta antes y marca capped=True."""
    from app.clients.scoring import ScoringResult

    def make_expensive_score(name: str) -> ScoringResult:
        return ScoringResult(
            response=CandidateFitResponse(
                score=6.0,
                rationale="aceptable rationale con suficiente longitud",
                gaps=[],
                strengths=[],
                recommended_next_step="psicometrico",
            ),
            input_tokens=100,
            output_tokens=50,
            cost_usd=10.0,
            model="gemini-1.5-flash",
        )

    async def expensive_score(candidate: dict, icp_text: str):  # noqa: ARG001
        return make_expensive_score(candidate.get("full_name", "x"))

    async def fake_embed(_text: str, *, model: str | None = None):  # noqa: ARG001
        # Embedding también caro para que cape antes del primer scoring.
        return _make_embedding_result(cost=0.05)

    async def fake_match(_db, _emb, *, limit: int = 50):
        return [
            hr_repo.CandidatoMatch(
                id=uuid4(), full_name=f"C{i}", headline=None, summary=None, distance=0.1,
            )
            for i in range(min(limit, 3))
        ]

    async def fake_set_tenant_context(_db, _e, *, role: str = "HR") -> None:  # noqa: ARG001
        return None

    async def fake_update_run(_db, **_kw):
        return None

    monkeypatch.setattr(sourcer_mod, "db_session", _fake_db_session)
    monkeypatch.setattr(sourcer_mod, "set_tenant_context", fake_set_tenant_context)
    monkeypatch.setattr(sourcer_mod, "embed_text", fake_embed)
    monkeypatch.setattr(sourcer_mod, "score_candidate_fit", expensive_score)
    monkeypatch.setattr(sourcer_mod.hr_repo, "match_candidates", fake_match)
    monkeypatch.setattr(sourcer_mod.hr_repo, "update_run_status", fake_update_run)

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
async def test_run_rejects_invalid_empresa_id() -> None:
    with pytest.raises(ValueError, match="empresa_id"):
        await sourcer_mod._run(
            run_id="00000000-0000-0000-0000-000000000013",
            empresa_id="not-a-uuid",
            icp_text="x",
        )


@pytest.mark.asyncio
async def test_run_requires_vacante_or_icp_text(patched_world: dict[str, Any]) -> None:  # noqa: ARG001
    with pytest.raises(ValueError, match="requerido"):
        await sourcer_mod._run(
            run_id="00000000-0000-0000-0000-000000000014",
            empresa_id=EMPRESA_ID,
        )
