"""Adaptadores de infraestructura: traducen entre los SDK y el dominio, y nada más."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest

from app.clients.embeddings import EmbeddingResult
from app.clients.scoring import CandidateFitResponse, LLMUnavailableError, ScoringResult
from app.domain.entidades import PerfilAnonimo
from app.domain.puertos import ProveedorNoDisponibleError
from app.infrastructure import cola
from app.infrastructure import evaluacion as evaluacion_mod
from app.repositories import hr as hr_repo

APP = Path(__file__).resolve().parents[2] / "app"


class TestEmbeddings:
    async def test_devuelve_el_vector_como_tupla(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def ok(_t: str, *, model: str | None = None) -> EmbeddingResult:
            return EmbeddingResult(vector=[0.1, 0.2], token_count=3, cost_usd=0.001, model="m")

        monkeypatch.setattr(evaluacion_mod, "embed_text", ok)
        emb = await evaluacion_mod.OpenAIEmbeddings().embed("Backend Python")
        assert emb.vector == (0.1, 0.2)
        assert emb.cost_usd == 0.001

    @pytest.mark.parametrize(
        "error",
        [httpx.ConnectTimeout("no responde"), RuntimeError("OPENAI_API_KEY no configurada")],
        ids=["caida", "sin-key"],
    )
    async def test_la_falta_de_proveedor_se_traduce_al_dominio(
        self, monkeypatch: pytest.MonkeyPatch, error: Exception
    ) -> None:
        async def falla(_t: str, *, model: str | None = None) -> EmbeddingResult:
            raise error

        monkeypatch.setattr(evaluacion_mod, "embed_text", falla)
        with pytest.raises(ProveedorNoDisponibleError):
            await evaluacion_mod.OpenAIEmbeddings().embed("Backend Python")

    async def test_un_error_que_no_es_de_disponibilidad_sale_tal_cual(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def vacio(_t: str, *, model: str | None = None) -> EmbeddingResult:
            raise ValueError("embed_text: input vacío")

        monkeypatch.setattr(evaluacion_mod, "embed_text", vacio)
        with pytest.raises(ValueError, match="input vacío"):
            await evaluacion_mod.OpenAIEmbeddings().embed("")


class TestScoring:
    async def test_al_modelo_solo_le_llega_el_perfil_anonimo(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recibido: dict[str, Any] = {}

        async def score(candidato: dict[str, Any], icp: str) -> ScoringResult:
            recibido.update(candidato=candidato, icp=icp)
            return ScoringResult(
                response=CandidateFitResponse(
                    score=7.5,
                    rationale="Encaje sólido con Python",
                    gaps=["Celery"],
                    strengths=["FastAPI"],
                    recommended_next_step="entrevista",
                ),
                input_tokens=1,
                output_tokens=1,
                cost_usd=0.0002,
                model="gemini-2.5-flash",
            )

        monkeypatch.setattr(evaluacion_mod, "score_candidate_fit", score)
        res = await evaluacion_mod.LlmScoring().score(
            PerfilAnonimo(headline="Backend Python", summary="8 años"), "ICP"
        )
        assert recibido["candidato"] == {"headline": "Backend Python", "summary": "8 años"}
        assert res.fit.score == 7.5
        assert res.fit.gaps == ("Celery",)
        assert res.model == "gemini-2.5-flash"

    def test_sin_modelos_es_falta_de_proveedor_para_el_dominio(self) -> None:
        # La tarea aplaza por `ProveedorNoDisponibleError`; el cliente lanza la suya.
        assert issubclass(LLMUnavailableError, ProveedorNoDisponibleError)


class TestRepositorio:
    async def test_traduce_filas_a_entidades(self, monkeypatch: pytest.MonkeyPatch) -> None:
        vid, cid, eid = uuid4(), uuid4(), uuid4()

        async def vacante(_db: object, _id: object) -> hr_repo.VacanteRow:
            return hr_repo.VacanteRow(
                id=vid, empresa_id=eid, title="t", jd="jd", icp_text=None,
                icp_embedding=None, status="open",
            )  # fmt: skip

        async def candidato(_db: object, _id: object) -> hr_repo.CandidatoRow:
            return hr_repo.CandidatoRow(
                id=cid, full_name="Ana", headline="h", summary=None, tiene_embedding=True
            )

        monkeypatch.setattr(hr_repo, "get_vacante", vacante)
        monkeypatch.setattr(hr_repo, "get_candidato", candidato)
        repo = evaluacion_mod.SqlCandidateRepository(db=object())  # type: ignore[arg-type]

        v = await repo.get_vacante(vid)
        c = await repo.get_candidato(cid)
        assert v is not None and v.tiene_embedding is False and v.icp == "jd"
        assert c is not None and c.tiene_embedding is True


class TestCola:
    def test_los_nombres_coinciden_con_las_tareas_registradas(self) -> None:
        from app.workers import cv_evaluator, sourcer

        assert cola.cv_evaluator_task.nombre == cv_evaluator.run.name
        assert cola.sourcer_task.nombre == sourcer.run.name

    @pytest.mark.parametrize("modulo", sorted((APP / "api").glob("*.py")), ids=lambda p: p.name)
    def test_la_api_no_importa_los_workers(self, modulo: Path) -> None:
        importados: list[str] = []
        for nodo in ast.walk(ast.parse(modulo.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.ImportFrom) and nodo.module:
                importados.append(nodo.module)
            elif isinstance(nodo, ast.Import):
                importados.extend(a.name for a in nodo.names)
        assert [m for m in importados if m.startswith("app.workers")] == []


def test_el_sql_solo_vive_en_los_repositorios() -> None:
    """`text(` de SQLAlchemy fuera de `app/repositories` es SQL suelto. Excepciones
    deliberadas: el contexto de tenant (`set_config`) y el `select 1` del health check."""
    permitidos = {"repositories", "security", "health.py"}
    sueltos = [
        str(p.relative_to(APP))
        for p in APP.rglob("*.py")
        if "text(" in p.read_text(encoding="utf-8")
        and "from sqlalchemy import text" in p.read_text(encoding="utf-8")
        and not ({p.parts[-2], p.name} & permitidos)
    ]
    assert sueltos == []
