"""La tarea de la evaluación con IA del plan de pago: la agenda de beat y el cableado (ADR-021)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest

from app.application.evaluar_aplicaciones import ResultadoDeLasEvaluaciones
from app.clients import scoring
from app.domain.anonimizacion import anonimizar
from app.infrastructure.evaluacion import LlmScoring
from app.workers import evaluaciones as worker
from app.workers.celery_app import celery_app


def test_beat_barre_cada_minuto() -> None:
    entrada = celery_app.conf.beat_schedule["evaluaciones-barrer"]
    assert (entrada["task"], entrada["schedule"]) == ("evaluaciones.barrer", 60.0)
    # Un barrido atrasado se descarta antes de que llegue el siguiente.
    assert entrada["options"]["expires"] < entrada["schedule"]
    assert "evaluaciones.barrer" in celery_app.tasks


def test_sin_storage_configurado_no_barre(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker.settings, "supabase_secret_key", "")

    async def no_deberia_correr() -> dict[str, Any]:
        raise AssertionError("sin Storage no hay barrido")

    monkeypatch.setattr(worker, "_barrer", no_deberia_correr)
    assert worker.barrer() == {}


async def test_el_barrido_usa_el_lote_el_paralelo_y_el_presupuesto_de_la_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recibido: dict[str, Any] = {}

    class CasoFalso:
        def __init__(self, *_adaptadores: Any, **opciones: Any) -> None:
            recibido.update(opciones)

        async def ejecutar(self, *, lote: int) -> ResultadoDeLasEvaluaciones:
            recibido["lote"] = lote
            return ResultadoDeLasEvaluaciones(evaluadas=3, costo_usd=0.0075)

    @asynccontextmanager
    async def sesion_falsa() -> AsyncIterator[object]:
        yield object()

    monkeypatch.setattr(worker, "EvaluarAplicacionesPendientes", CasoFalso)
    monkeypatch.setattr(worker, "db_session", sesion_falsa)
    monkeypatch.setattr(worker.settings, "evaluaciones_lote", 7)
    monkeypatch.setattr(worker.settings, "evaluaciones_en_paralelo", 2)
    monkeypatch.setattr(worker.settings, "ia_presupuesto_mensual_usd", 10.0)

    resultado = await worker._barrer()

    assert resultado["evaluadas"] == 3
    assert recibido == {"lote": 7, "en_paralelo": 2, "presupuesto_mensual_usd": 10.0}


def test_la_config_trae_topes_razonables() -> None:
    campos = worker.settings.model_fields
    assert campos["evaluaciones_lote"].default == 50
    assert campos["evaluaciones_en_paralelo"].default == 8
    assert campos["ia_presupuesto_mensual_usd"].default == 25.0


async def test_al_modelo_le_llega_el_cv_anonimizado_y_no_el_titular(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llamadas: list[tuple[dict[str, Any], str]] = []

    async def puntuar(candidato: dict[str, Any], icp: str) -> Any:
        llamadas.append((candidato, icp))
        raise RuntimeError("basta con ver qué recibe")

    monkeypatch.setattr("app.infrastructure.evaluacion.score_candidate_fit", puntuar)
    cv = anonimizar("Ana Paz\nAnalista con Python y SQL.", nombre="Ana Paz")

    with pytest.raises(RuntimeError):
        await LlmScoring().evaluar(cv, "Puesto: Analista")

    assert llamadas == [({"cv": cv.texto}, "Puesto: Analista")]


def test_el_prompt_con_cv_lo_lleva_como_texto_y_sin_campos_del_perfil() -> None:
    prompt = scoring._build_prompt({"cv": "[nombre]\nAnalista con Python."}, "Puesto: Analista")
    assert "## CV del candidato (anonimizado)\n[nombre]\nAnalista con Python." in prompt
    assert "headline" not in prompt.split("## Schema")[0]
    assert "Puesto: Analista" in prompt


def test_el_prompt_sin_cv_sigue_con_titular_y_resumen() -> None:
    prompt = scoring._build_prompt({"headline": "Senior Python", "summary": None}, "ICP")
    assert '"headline": "Senior Python"' in prompt
    assert "CV del candidato" not in prompt
