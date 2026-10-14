"""El siguiente paso de un candidato lo decide una regla fija, no el modelo."""

from __future__ import annotations

from typing import Any

import pytest

from app.clients import scoring
from app.clients.scoring import CandidateFitResponse, ScoringResult
from app.domain.siguiente_paso import siguiente_paso


@pytest.mark.parametrize(
    ("score", "esperado"),
    [
        (0.0, "rechazar"),
        (3.9, "rechazar"),
        (4.0, "psicometrico"),
        (6.0, "psicometrico"),
        # 6.5 caía en el hueco entre los tramos 4-6 y 7-8 del SKILL.md.
        (6.5, "psicometrico"),
        (6.99, "psicometrico"),
        (7.0, "entrevista"),
        (10.0, "entrevista"),
    ],
)
def test_tramos_sin_huecos(score: float, esperado: str) -> None:
    assert siguiente_paso(score) == esperado


def _proveedor_que_sugiere(score: float, sugerido: str) -> Any:
    async def puntuar(_c: dict[str, Any], _icp: str) -> ScoringResult:
        return ScoringResult(
            response=CandidateFitResponse(
                score=score,
                rationale="Match fuerte con el ICP",
                gaps=[],
                strengths=["python"],
                recommended_next_step=sugerido,  # type: ignore[arg-type]
            ),
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0,
            model="gemini-2.5-flash",
        )

    return puntuar


@pytest.mark.asyncio
async def test_un_85_con_rechazar_sale_como_entrevista(monkeypatch: pytest.MonkeyPatch) -> None:
    """Antes se aceptaba tal cual: una decisión sobre una persona sin regla."""
    monkeypatch.setattr(
        scoring, "_PROVEEDORES", (("gemini", _proveedor_que_sugiere(8.5, "rechazar")),)
    )
    r = await scoring.score_candidate_fit({"full_name": "Ana"}, "ICP")
    assert r.response.recommended_next_step == "entrevista"
    assert r.response.score == 8.5


@pytest.mark.asyncio
async def test_si_el_modelo_coincide_no_se_toca(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        scoring, "_PROVEEDORES", (("gemini", _proveedor_que_sugiere(2.0, "rechazar")),)
    )
    r = await scoring.score_candidate_fit({"full_name": "Ana"}, "ICP")
    assert r.response.recommended_next_step == "rechazar"
