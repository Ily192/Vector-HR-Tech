"""La tarea del aviso de los diagnósticos: la agenda de beat y el cableado (migración 0017)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest

from app.application.avisar_diagnosticos import ResultadoDelAviso
from app.infrastructure.diagnosticos import CorreoSmtp, TurnstileCloudflare
from app.workers import diagnosticos as worker
from app.workers.celery_app import celery_app


def test_beat_avisa_cada_minuto() -> None:
    entrada = celery_app.conf.beat_schedule["diagnosticos-avisar"]
    assert (entrada["task"], entrada["schedule"]) == ("diagnosticos.avisar", 60.0)
    # El token de Turnstile dura 300 s, y un barrido atrasado se descarta.
    assert entrada["options"]["expires"] < entrada["schedule"]
    celery_app.loader.import_default_modules()
    assert "diagnosticos.avisar" in celery_app.tasks


def _capturar(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    capturado: dict[str, Any] = {}

    class CasoFalso:
        def __init__(self, _repo: object, verificador: object, correo: object, **kw: Any) -> None:
            capturado.update(verificador=verificador, correo=correo, **kw)

        async def ejecutar(self) -> ResultadoDelAviso:
            return ResultadoDelAviso(avisados=2, sin_detalle=1)

    @asynccontextmanager
    async def sesion_falsa() -> AsyncIterator[object]:
        yield object()

    monkeypatch.setattr(worker, "AvisarDiagnosticos", CasoFalso)
    monkeypatch.setattr(worker, "db_session", sesion_falsa)
    return capturado


async def test_con_todo_configurado_usa_resend_y_turnstile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capturado = _capturar(monkeypatch)
    monkeypatch.setattr(worker.settings, "smtp_pass", "re_clave")
    monkeypatch.setattr(worker.settings, "smtp_remitente", "no-responder@vectorhrtech.com")
    monkeypatch.setattr(worker.settings, "turnstile_secret_key", "secreto")
    monkeypatch.setattr(worker.settings, "aviso_diagnosticos_max_dia", 7)

    assert await worker._avisar() == {
        "avisados": 2,
        "sin_detalle": 1,
        "descartados": 0,
        "en_espera": 0,
        "sin_avisar": 0,
    }
    assert isinstance(capturado["correo"], CorreoSmtp)
    assert isinstance(capturado["verificador"], TurnstileCloudflare)
    assert capturado["para"] == "hola@vectorhrtech.com"
    assert capturado["max_por_dia"] == 7


@pytest.mark.parametrize("falta", ["smtp_pass", "smtp_remitente"])
async def test_sin_smtp_no_hay_correo(monkeypatch: pytest.MonkeyPatch, falta: str) -> None:
    capturado = _capturar(monkeypatch)
    monkeypatch.setattr(worker.settings, "smtp_pass", "re_clave")
    monkeypatch.setattr(worker.settings, "smtp_remitente", "no-responder@vectorhrtech.com")
    monkeypatch.setattr(worker.settings, falta, "")

    await worker._avisar()

    assert capturado["correo"] is None


async def test_sin_secreto_de_turnstile_no_se_verifica(monkeypatch: pytest.MonkeyPatch) -> None:
    capturado = _capturar(monkeypatch)
    monkeypatch.setattr(worker.settings, "turnstile_secret_key", "")

    await worker._avisar()

    assert capturado["verificador"] is None


def test_el_aviso_no_importa_ningun_cliente_de_llm() -> None:
    from app.infrastructure import diagnosticos as adaptadores

    for modulo in (worker, adaptadores):
        codigo = Path(str(modulo.__file__)).read_text(encoding="utf-8")
        for cliente in ("app.clients", "openai", "google.genai"):
            assert cliente not in codigo, (modulo.__name__, cliente)
