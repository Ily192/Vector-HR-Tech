"""El área de admin (ADR-022, enmienda del 2026-11-17): quién entra, `GET /auth/v1/user`
y los conteos del tablero."""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from app.domain.admin import AuthNoDisponibleError, UsuarioDeAuth, es_admin
from app.domain.moderacion import EstadoDeModeracion
from app.infrastructure import admin as infra
from app.infrastructure.admin import SesionesSupabase, SqlResumenDeLaPlataforma

PERMITIDOS = frozenset({"hola@vectorhrtech.com"})


@pytest.mark.parametrize(
    ("usuario", "entra"),
    [
        (UsuarioDeAuth("hola@vectorhrtech.com", confirmado=True), True),
        (UsuarioDeAuth(" HOLA@VectorHRTech.com ", confirmado=True), True),
        (UsuarioDeAuth("hola@vectorhrtech.com", confirmado=False), False),
        (UsuarioDeAuth("rh@andes.mx", confirmado=True), False),
        (UsuarioDeAuth("hola@vectorhrtech.com.mx", confirmado=True), False),
    ],
)
def test_entra_solo_un_correo_confirmado_de_la_lista(usuario: UsuarioDeAuth, entra: bool) -> None:
    assert es_admin(usuario, PERMITIDOS) is entra


def test_con_la_lista_vacia_no_entra_nadie() -> None:
    assert not es_admin(UsuarioDeAuth("hola@vectorhrtech.com", confirmado=True), frozenset())


# ─────────────────────────────── GET /auth/v1/user ───────────────────────────────


def _sesiones(
    responder: Callable[[httpx.Request], httpx.Response],
) -> tuple[SesionesSupabase, httpx.AsyncClient]:
    http = httpx.AsyncClient(transport=httpx.MockTransport(responder))
    return SesionesSupabase("http://api-gw:8000/", "sb_secret_de_prueba", http), http


async def test_le_pregunta_a_auth_con_la_apikey_y_el_token_de_la_sesion() -> None:
    peticiones: list[httpx.Request] = []

    def responder(peticion: httpx.Request) -> httpx.Response:
        peticiones.append(peticion)
        return httpx.Response(
            200, json={"email": "hola@vectorhrtech.com", "email_confirmed_at": "2026-11-17T10:00Z"}
        )

    sesiones, http = _sesiones(responder)
    async with http:
        usuario = await sesiones.usuario("token-de-la-sesion")

    assert usuario == UsuarioDeAuth("hola@vectorhrtech.com", confirmado=True)
    (peticion,) = peticiones
    assert (peticion.method, str(peticion.url)) == ("GET", "http://api-gw:8000/auth/v1/user")
    assert peticion.headers["apikey"] == "sb_secret_de_prueba"
    assert peticion.headers["Authorization"] == "Bearer token-de-la-sesion"


async def test_sin_confirmar_el_correo() -> None:
    sesiones, http = _sesiones(
        lambda _: httpx.Response(200, json={"email": "a@b.mx", "email_confirmed_at": None})
    )
    async with http:
        assert await sesiones.usuario("t") == UsuarioDeAuth("a@b.mx", confirmado=False)


@pytest.mark.parametrize("estado", [401, 403, 404])
async def test_un_token_que_no_sirve_es_none(estado: int) -> None:
    sesiones, http = _sesiones(
        lambda _: httpx.Response(estado, json={"code": "bad_jwt", "message": "x"})
    )
    async with http:
        assert await sesiones.usuario("t") is None


@pytest.mark.parametrize("cuerpo", [{}, {"email": ""}, {"email": 3}, []])
async def test_una_cuenta_sin_correo_es_none(cuerpo: Any) -> None:
    sesiones, http = _sesiones(lambda _: httpx.Response(200, json=cuerpo))
    async with http:
        assert await sesiones.usuario("t") is None


@pytest.mark.parametrize(
    "responder",
    [
        lambda _: httpx.Response(500, json={}),
        lambda _: httpx.Response(429, json={}),
        lambda _: httpx.Response(200, text="<html>"),
    ],
    ids=["500", "429", "no-json"],
)
async def test_si_auth_falla_no_se_sabe_de_quien_es(
    responder: Callable[[httpx.Request], httpx.Response],
) -> None:
    sesiones, http = _sesiones(responder)
    async with http:
        with pytest.raises(AuthNoDisponibleError):
            await sesiones.usuario("t")


async def test_si_auth_no_contesta() -> None:
    def responder(peticion: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("lento", request=peticion)

    sesiones, http = _sesiones(responder)
    async with http:
        with pytest.raises(AuthNoDisponibleError):
            await sesiones.usuario("t")


# ─────────────────────────────── los conteos ───────────────────────────────


async def test_el_resumen_trae_los_cinco_estados_aunque_falten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conteos = SimpleNamespace(
        empresas=10,
        empresas_verificadas=3,
        altas_web_confirmadas=6,
        altas_ultimos_7_dias=2,
        vacantes_abiertas=8,
        vacantes_cerradas=4,
        aplicaciones=50,
        aplicaciones_ultimos_7_dias=9,
    )

    async def falsos_conteos(_db: object) -> SimpleNamespace:
        return conteos

    async def falso_por_moderacion(_db: object) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(estado="publicada", n=6),
            SimpleNamespace(estado="en_revision", n=2),
        ]

    monkeypatch.setattr(infra.admin_repo, "conteos", falsos_conteos)
    monkeypatch.setattr(infra.admin_repo, "por_moderacion", falso_por_moderacion)
    resumen = await SqlResumenDeLaPlataforma(object()).resumen()  # type: ignore[arg-type]

    assert dict(resumen.vacantes_por_moderacion) == {
        EstadoDeModeracion.PENDIENTE: 0,
        EstadoDeModeracion.PUBLICADA: 6,
        EstadoDeModeracion.EN_REVISION: 2,
        EstadoDeModeracion.RECHAZADA: 0,
        EstadoDeModeracion.OCULTA: 0,
    }
    assert (resumen.empresas, resumen.altas_web_confirmadas, resumen.aplicaciones) == (10, 6, 50)
