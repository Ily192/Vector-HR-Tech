"""`POST /alta/plan-gratis`: el secreto, el body exacto y cómo se traduce cada error."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient

from app.api import alta
from app.application.alta_desde_la_web import RespuestaDelAlta
from app.config import settings
from app.domain.alta_web import SolicitudDeAltaWeb
from app.domain.puertos import CodigoNoEnviadoError, LimiteDeAltasError

from .test_alta_web import datos

SECRETO = "secreto-de-prueba-del-alta"
RUTA = "/alta/plan-gratis"


class CasoFalso:
    """Ocupa el lugar de `DarDeAltaDesdeLaWeb`: sin base ni Auth."""

    recibido: ClassVar[list[tuple[SolicitudDeAltaWeb, str | None]]] = []
    falla: ClassVar[Exception | None] = None

    def __init__(self, *_: object) -> None: ...

    async def ejecutar(
        self, solicitud: SolicitudDeAltaWeb, ip_hash: str | None
    ) -> RespuestaDelAlta:
        if CasoFalso.falla:
            raise CasoFalso.falla
        CasoFalso.recibido.append((solicitud, ip_hash))
        return RespuestaDelAlta("https://panel.vectorhrtech.com/verificar#correo=x")


@pytest.fixture
def con_secreto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "alta_secreto", SECRETO)
    monkeypatch.setattr(alta, "DarDeAltaDesdeLaWeb", CasoFalso)
    CasoFalso.recibido, CasoFalso.falla = [], None


def _cuerpo(**cambios: object) -> dict[str, Any]:
    cuerpo = datos(**cambios)
    cuerpo["lead_id"] = 1024
    return cuerpo


def _cabeceras(secreto: str = SECRETO) -> dict[str, str]:
    return {"Authorization": f"Bearer {secreto}"}


def test_sin_secreto_configurado_el_alta_esta_apagada(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "alta_secreto", "")
    respuesta = client.post(RUTA, json=_cuerpo(), headers=_cabeceras())
    assert respuesta.status_code == 503


@pytest.mark.usefixtures("con_secreto")
@pytest.mark.parametrize("cabeceras", [{}, _cabeceras("otro"), {"Authorization": SECRETO}])
def test_sin_el_secreto_es_401_antes_de_mirar_el_body(
    client: TestClient, cabeceras: dict[str, str]
) -> None:
    respuesta = client.post(RUTA, json={"cualquier": "cosa"}, headers=cabeceras)
    assert respuesta.status_code == 401
    assert respuesta.headers["WWW-Authenticate"] == "Bearer"
    assert CasoFalso.recibido == []


@pytest.mark.usefixtures("con_secreto")
def test_con_el_secreto_responde_lo_mismo_para_todos(client: TestClient) -> None:
    respuesta = client.post(RUTA, json=_cuerpo(), headers=_cabeceras())
    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "estado": "codigo_enviado",
        "verificar_url": "https://panel.vectorhrtech.com/verificar#correo=x",
    }
    assert respuesta.headers["Cache-Control"] == "no-store"
    ((solicitud, ip_hash),) = CasoFalso.recibido
    assert solicitud.lead_id == "1024"
    assert ip_hash is not None and "203.0.113.7" not in ip_hash


@pytest.mark.usefixtures("con_secreto")
@pytest.mark.parametrize(
    "cuerpo",
    [
        _cuerpo(turnstile_token="x"),  # Turnstile lo valida la web
        _cuerpo(pais="co"),
        _cuerpo(web_empresa=None, linkedin=None),
        _cuerpo(correo="no-es-un-correo"),
        {k: v for k, v in _cuerpo().items() if k != "correo"},
    ],
)
def test_datos_que_no_sirven_son_422(client: TestClient, cuerpo: dict[str, Any]) -> None:
    respuesta = client.post(RUTA, json=cuerpo, headers=_cabeceras())
    assert respuesta.status_code == 422
    assert CasoFalso.recibido == []


@pytest.mark.usefixtures("con_secreto")
def test_pasado_el_tope_es_429_con_retry_after(client: TestClient) -> None:
    CasoFalso.falla = LimiteDeAltasError(321)
    respuesta = client.post(RUTA, json=_cuerpo(), headers=_cabeceras())
    assert respuesta.status_code == 429
    assert respuesta.headers["Retry-After"] == "321"


@pytest.mark.usefixtures("con_secreto")
def test_si_auth_no_responde_es_503(client: TestClient) -> None:
    CasoFalso.falla = CodigoNoEnviadoError("Auth caído")
    respuesta = client.post(RUTA, json=_cuerpo(), headers=_cabeceras())
    assert respuesta.status_code == 503
