"""Las tareas de la coincidencia de skills: la agenda de beat y el cableado (ADR-019)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from celery.schedules import crontab

from app.application.coincidir_cvs import ResultadoDelBarrido
from app.workers import coincidencias as worker
from app.workers.celery_app import celery_app


def test_beat_barre_cada_minuto_y_purga_una_vez_al_dia() -> None:
    agenda = celery_app.conf.beat_schedule
    barrer, purgar = agenda["coincidencias-barrer"], agenda["coincidencias-purgar"]
    assert (barrer["task"], barrer["schedule"]) == ("coincidencias.barrer", 60.0)
    # Un barrido atrasado se descarta antes de que llegue el siguiente.
    assert barrer["options"]["expires"] < barrer["schedule"]
    assert purgar["task"] == "coincidencias.purgar"
    assert isinstance(purgar["schedule"], crontab)
    for entrada in agenda.values():
        assert entrada["task"] in celery_app.tasks


def test_sin_storage_configurado_no_barre(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker.settings, "supabase_url", "")

    async def no_deberia_correr() -> dict[str, int]:
        raise AssertionError("sin Storage no hay barrido")

    monkeypatch.setattr(worker, "_barrer", no_deberia_correr)
    assert worker.barrer() == {}


async def test_el_barrido_llama_al_caso_de_uso_con_el_lote_de_la_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lotes: list[int] = []

    class CasoFalso:
        def __init__(self, *_adaptadores: Any) -> None:
            pass

        async def ejecutar(self, *, lote: int) -> ResultadoDelBarrido:
            lotes.append(lote)
            return ResultadoDelBarrido(revisados=2, ilegibles=1)

    @asynccontextmanager
    async def sesion_falsa() -> AsyncIterator[object]:
        yield object()

    monkeypatch.setattr(worker, "CoincidirCvsPendientes", CasoFalso)
    monkeypatch.setattr(worker, "db_session", sesion_falsa)
    monkeypatch.setattr(worker.settings, "coincidencias_lote", 7)

    assert await worker._barrer() == {
        "revisados": 2,
        "ilegibles": 1,
        "descartados": 0,
        "en_espera": 0,
    }
    assert lotes == [7]


def test_el_worker_no_importa_ningun_cliente_de_llm() -> None:
    """La coincidencia es sin IA: ni el worker ni sus adaptadores tocan un LLM."""
    from app.infrastructure import coincidencias as adaptadores

    for modulo in (worker, adaptadores):
        codigo = Path(str(modulo.__file__)).read_text(encoding="utf-8")
        for cliente in ("app.clients", "openai", "google.genai"):
            assert cliente not in codigo, (modulo.__name__, cliente)
