"""Reglas de las entidades de la evaluación. Puras: sin base, sin red y sin mocks."""

from __future__ import annotations

import dataclasses
import math
from uuid import uuid4

import pytest

from app.domain.entidades import Candidato, FitScore, PerfilAnonimo, Vacante

RAZONAMIENTO = "Encaja en Python y FastAPI; le falta experiencia con Celery."


def _candidato(headline: str | None, summary: str | None) -> Candidato:
    return Candidato(
        id=uuid4(),
        full_name="Ana Pérez",
        headline=headline,
        summary=summary,
        tiene_embedding=False,
    )


def _vacante(icp_text: str | None) -> Vacante:
    return Vacante(
        id=uuid4(),
        empresa_id=uuid4(),
        title="Backend Engineer",
        jd="Servicios Python multi-tenant.",
        icp_text=icp_text,
        tiene_embedding=False,
    )


class TestCandidato:
    def test_el_perfil_que_ve_el_modelo_no_lleva_el_nombre(self) -> None:
        perfil = _candidato("Backend Python", "8 años con FastAPI").perfil_anonimo()

        assert perfil == PerfilAnonimo(headline="Backend Python", summary="8 años con FastAPI")
        assert "full_name" not in {f.name for f in dataclasses.fields(perfil)}
        assert "Ana" not in repr(perfil)

    def test_el_texto_del_embedding_no_lleva_el_nombre(self) -> None:
        texto = _candidato("Backend Python", "8 años con FastAPI").texto_para_embedding()

        assert texto == "Backend Python\n8 años con FastAPI"
        assert "Ana" not in texto

    @pytest.mark.parametrize(
        ("headline", "summary", "esperado"),
        [
            (None, "8 años con FastAPI", "8 años con FastAPI"),
            ("Backend Python", None, "Backend Python"),
            ("", "8 años con FastAPI", "8 años con FastAPI"),
            (None, None, ""),
        ],
    )
    def test_el_texto_del_embedding_omite_lo_que_falta(
        self, headline: str | None, summary: str | None, esperado: str
    ) -> None:
        assert _candidato(headline, summary).texto_para_embedding() == esperado


class TestVacante:
    def test_se_evalua_contra_su_icp(self) -> None:
        assert _vacante("Senior, Python, multi-tenant").icp == "Senior, Python, multi-tenant"

    @pytest.mark.parametrize("icp_text", [None, ""])
    def test_sin_icp_escrito_se_evalua_contra_la_descripcion(self, icp_text: str | None) -> None:
        assert _vacante(icp_text).icp == "Servicios Python multi-tenant."


class TestFitScore:
    @pytest.mark.parametrize("score", [0.0, 6.5, 10.0])
    def test_acepta_scores_dentro_de_la_escala(self, score: float) -> None:
        assert FitScore(score=score, rationale=RAZONAMIENTO).score == score

    @pytest.mark.parametrize("score", [-0.1, 10.1, math.nan, math.inf])
    def test_un_score_fuera_de_la_escala_no_existe(self, score: float) -> None:
        with pytest.raises(ValueError, match="score fuera de"):
            FitScore(score=score, rationale=RAZONAMIENTO)

    def test_el_razonamiento_tiene_un_minimo_como_en_el_contrato(self) -> None:
        assert FitScore(score=5, rationale="x" * 10).rationale == "x" * 10
        with pytest.raises(ValueError, match="razonamiento"):
            FitScore(score=5, rationale="x" * 9)

    @pytest.mark.parametrize(
        ("score", "paso"),
        [(3.9, "rechazar"), (4.0, "psicometrico"), (6.5, "psicometrico"), (7.0, "entrevista")],
    )
    def test_el_siguiente_paso_lo_decide_la_politica(self, score: float, paso: str) -> None:
        assert FitScore(score=score, rationale=RAZONAMIENTO).siguiente_paso == paso

    def test_es_inmutable(self) -> None:
        fit = FitScore(score=8, rationale=RAZONAMIENTO)
        with pytest.raises(dataclasses.FrozenInstanceError):
            fit.score = 2  # type: ignore[misc]
