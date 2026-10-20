"""El adaptador de la API de administración de Supabase Auth (`POST /auth/v1/invite`)."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from app.domain.puertos import CuentaYaExisteError, InvitacionNoEnviadaError
from app.infrastructure.altas import InvitacionesSupabase

URL = "https://proyecto.supabase.co/"
PANEL = "https://panel.vectorhr.tech/"


def _servicio(
    responder: Callable[[httpx.Request], httpx.Response], clave: str = "sb_secret_de_prueba"
) -> tuple[InvitacionesSupabase, httpx.AsyncClient]:
    http = httpx.AsyncClient(transport=httpx.MockTransport(responder))
    return InvitacionesSupabase(URL, clave, PANEL, http), http


async def test_invita_con_el_token_en_el_metadata_y_vuelve_al_panel() -> None:
    peticiones: list[httpx.Request] = []

    def responder(peticion: httpx.Request) -> httpx.Response:
        peticiones.append(peticion)
        return httpx.Response(200, json={"id": "usuario-1"})

    servicio, http = _servicio(responder)
    async with http:
        await servicio.invitar("ana@ferreterianorte.mx", "token-de-prueba", "Ana Ruiz")

    (peticion,) = peticiones
    assert (peticion.method, str(peticion.url.copy_with(query=None))) == (
        "POST",
        "https://proyecto.supabase.co/auth/v1/invite",
    )
    assert peticion.url.params["redirect_to"] == PANEL
    assert peticion.headers["apikey"] == "sb_secret_de_prueba"
    assert peticion.headers["x-supabase-api-version"] == "2024-01-01"
    # La clave nueva va solo en `apikey`.
    assert "authorization" not in peticion.headers
    assert json.loads(peticion.content) == {
        "email": "ana@ferreterianorte.mx",
        "data": {"invite_token": "token-de-prueba", "full_name": "Ana Ruiz"},
    }


async def test_la_service_role_legada_va_tambien_como_bearer() -> None:
    peticiones: list[httpx.Request] = []

    def responder(peticion: httpx.Request) -> httpx.Response:
        peticiones.append(peticion)
        return httpx.Response(200, json={})

    servicio, http = _servicio(responder, clave="eyJhbGciOiJIUzI1NiJ9.legada.firma")
    async with http:
        await servicio.reenviar("ana@ferreterianorte.mx")
    assert peticiones[0].headers["authorization"] == "Bearer eyJhbGciOiJIUzI1NiJ9.legada.firma"
    # Reenviar no manda metadata: la cuenta ya existe y su empresa también.
    assert json.loads(peticiones[0].content) == {"email": "ana@ferreterianorte.mx"}


@pytest.mark.parametrize(
    ("estado", "cuerpo", "error"),
    [
        (
            422,
            {
                "code": "email_exists",
                "message": "A user with this email address has already been registered",
            },
            CuentaYaExisteError,
        ),
        # Sin la cabecera de versión, Auth contesta con el formato viejo.
        (422, {"code": 422, "error_code": "email_exists", "msg": "…"}, CuentaYaExisteError),
        (429, {"code": "over_email_send_rate_limit", "message": "…"}, InvitacionNoEnviadaError),
        (
            500,
            {"code": "unexpected_failure", "message": "Database error"},
            InvitacionNoEnviadaError,
        ),
        (502, "<html>Bad Gateway</html>", InvitacionNoEnviadaError),
    ],
)
async def test_traduce_las_respuestas_de_error(
    estado: int, cuerpo: object, error: type[Exception]
) -> None:
    def responder(_: httpx.Request) -> httpx.Response:
        if isinstance(cuerpo, str):
            return httpx.Response(estado, text=cuerpo)
        return httpx.Response(estado, json=cuerpo)

    servicio, http = _servicio(responder)
    async with http:
        with pytest.raises(error):
            await servicio.invitar("ana@ferreterianorte.mx", "token", "Ana Ruiz")


async def test_si_auth_no_responde_la_invitacion_no_salio() -> None:
    def responder(peticion: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red", request=peticion)

    servicio, http = _servicio(responder)
    async with http:
        with pytest.raises(InvitacionNoEnviadaError, match="ConnectError"):
            await servicio.invitar("ana@ferreterianorte.mx", "token", "Ana Ruiz")
