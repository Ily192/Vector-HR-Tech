"""Los adaptadores del alta desde la web: `POST /auth/v1/otp`, el borrado y los topes."""

from __future__ import annotations

import json
from collections.abc import Callable
from uuid import uuid4

import httpx
import pytest

from app.domain.puertos import (
    CodigoNoEnviadoError,
    CodigoReenviadoMuyProntoError,
    LimiteDeAltasError,
)
from app.infrastructure.altas_web import CodigosSupabase, LimitadorConLimits

URL = "https://api.vectorhrtech.com/"


def _servicio(
    responder: Callable[[httpx.Request], httpx.Response], clave: str = "eyJ.legada.service"
) -> tuple[CodigosSupabase, httpx.AsyncClient]:
    http = httpx.AsyncClient(transport=httpx.MockTransport(responder))
    return CodigosSupabase(URL, clave, http), http


def _error(estado: int, codigo: str) -> httpx.Response:
    return httpx.Response(estado, json={"code": codigo, "message": "x"})


async def test_el_alta_crea_la_cuenta_con_el_token_y_pasa_la_ip_del_visitante() -> None:
    peticiones: list[httpx.Request] = []

    def responder(peticion: httpx.Request) -> httpx.Response:
        peticiones.append(peticion)
        return httpx.Response(200, json={})

    servicio, http = _servicio(responder)
    async with http:
        await servicio.mandar_codigo_de_alta("ana@fn.mx", "token-1", "Ana Ruiz", "203.0.113.7")

    (peticion,) = peticiones
    assert (peticion.method, str(peticion.url)) == (
        "POST",
        "https://api.vectorhrtech.com/auth/v1/otp",
    )
    assert json.loads(peticion.content) == {
        "email": "ana@fn.mx",
        "create_user": True,
        "data": {"invite_token": "token-1", "full_name": "Ana Ruiz"},
    }
    assert peticion.headers["apikey"] == "eyJ.legada.service"
    assert peticion.headers["Authorization"] == "Bearer eyJ.legada.service"
    assert peticion.headers["CF-Connecting-IP"] == "203.0.113.7"


async def test_la_entrada_no_crea_cuentas_y_sin_ip_no_inventa_la_cabecera() -> None:
    peticiones: list[httpx.Request] = []

    def responder(peticion: httpx.Request) -> httpx.Response:
        peticiones.append(peticion)
        return httpx.Response(200, json={})

    servicio, http = _servicio(responder, clave="sb_secret_nueva")
    async with http:
        await servicio.mandar_codigo_de_entrada("ana@fn.mx", None)

    (peticion,) = peticiones
    assert json.loads(peticion.content) == {"email": "ana@fn.mx", "create_user": False}
    assert "CF-Connecting-IP" not in peticion.headers
    assert "Authorization" not in peticion.headers


async def test_un_codigo_reciente_no_es_error_para_quien_ya_tiene_cuenta() -> None:
    servicio, http = _servicio(lambda _: _error(429, "over_email_send_rate_limit"))
    async with http:
        with pytest.raises(CodigoReenviadoMuyProntoError):
            await servicio.mandar_codigo_de_entrada("ana@fn.mx", None)
        # A una cuenta nueva no le aplica la espera: es el tope por hora de Auth.
        with pytest.raises(CodigoNoEnviadoError):
            await servicio.mandar_codigo_de_alta("ana@fn.mx", "t", "Ana", None)


async def test_si_auth_corta_por_ip_es_un_tope_de_altas() -> None:
    servicio, http = _servicio(lambda _: _error(429, "over_request_rate_limit"))
    async with http:
        with pytest.raises(LimiteDeAltasError):
            await servicio.mandar_codigo_de_alta("ana@fn.mx", "t", "Ana", "203.0.113.7")


@pytest.mark.parametrize("respuesta", [_error(500, "unexpected_failure"), httpx.Response(502)])
async def test_cualquier_otra_respuesta_es_que_no_salio(respuesta: httpx.Response) -> None:
    servicio, http = _servicio(lambda _: respuesta)
    async with http:
        with pytest.raises(CodigoNoEnviadoError):
            await servicio.mandar_codigo_de_alta("ana@fn.mx", "t", "Ana", None)


async def test_sin_red_es_que_no_salio() -> None:
    def responder(peticion: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red", request=peticion)

    servicio, http = _servicio(responder)
    async with http:
        with pytest.raises(CodigoNoEnviadoError):
            await servicio.mandar_codigo_de_entrada("ana@fn.mx", None)


async def test_borrar_una_cuenta_que_ya_no_estaba_no_es_error() -> None:
    peticiones: list[httpx.Request] = []

    def responder(peticion: httpx.Request) -> httpx.Response:
        peticiones.append(peticion)
        return _error(404, "user_not_found")

    servicio, http = _servicio(responder)
    usuario = uuid4()
    async with http:
        await servicio.borrar_usuario(usuario)
    assert (peticiones[0].method, peticiones[0].url.path) == (
        "DELETE",
        f"/auth/v1/admin/users/{usuario}",
    )

    servicio, http = _servicio(lambda _: _error(500, "unexpected_failure"))
    async with http:
        with pytest.raises(CodigoNoEnviadoError):
            await servicio.borrar_usuario(usuario)


async def test_el_tope_por_correo_corta_al_cuarto_registro_de_la_hora() -> None:
    limitador = LimitadorConLimits("memory://", por_ip="5/hour", por_correo="3/hour")
    for _ in range(3):
        await limitador.consumir(None, "ana@fn.mx")
    with pytest.raises(LimiteDeAltasError) as error:
        await limitador.consumir(None, "ana@fn.mx")
    assert 1 <= error.value.reintentar_en_s <= 3601
    # Otro correo sigue pudiendo.
    await limitador.consumir(None, "otro@fn.mx")


async def test_el_tope_por_ip_corta_aunque_cambie_el_correo() -> None:
    limitador = LimitadorConLimits("memory://", por_ip="2/hour", por_correo="3/hour")
    await limitador.consumir("ip-1", "a@fn.mx")
    await limitador.consumir("ip-1", "b@fn.mx")
    with pytest.raises(LimiteDeAltasError):
        await limitador.consumir("ip-1", "c@fn.mx")
    # El intento cortado no gastó el cupo de su correo.
    await limitador.consumir("ip-2", "c@fn.mx")


async def test_sin_redis_el_alta_no_se_corta() -> None:
    limitador = LimitadorConLimits("memory://", por_ip="5/hour", por_correo="3/hour")

    def caido(*_: object) -> None:
        raise ConnectionError("redis no responde")

    limitador._consumir = caido  # type: ignore[method-assign]
    await limitador.consumir("ip", "ana@fn.mx")
