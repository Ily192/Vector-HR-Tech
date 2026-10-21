"""Los adaptadores del aviso de los diagnósticos: el SMTP (con uno falso) y Turnstile."""

from __future__ import annotations

import email
import json
import smtplib
from email import policy
from typing import Any, ClassVar

import httpx
import pytest

from app.domain.diagnostico import CorreoSaliente, resumen
from app.domain.puertos import CorreoNoEnviadoError, VerificadorNoDisponibleError
from app.infrastructure import diagnosticos as adaptadores
from app.infrastructure.diagnosticos import VERIFICAR_TURNSTILE, CorreoSmtp, TurnstileCloudflare

from .test_diagnostico import PARA, diagnostico


class SmtpFalso:
    """Lo que el adaptador le hace a `smtplib.SMTP`, sin red. Guarda cada paso."""

    instancias: ClassVar[list[SmtpFalso]] = []
    falla_en: ClassVar[str | None] = None

    def __init__(self, host: str, puerto: int, timeout: float) -> None:
        self.conexion = (host, puerto, timeout)
        self.pasos: list[str] = []
        self.login_con: tuple[str, str] | None = None
        self.mensajes: list[email.message.EmailMessage] = []
        SmtpFalso.instancias.append(self)
        self._fallar("conectar")

    def _fallar(self, paso: str) -> None:
        if SmtpFalso.falla_en == paso:
            excepciones: dict[str, Exception] = {
                "conectar": ConnectionRefusedError("sin SMTP"),
                "starttls": smtplib.SMTPNotSupportedError("STARTTLS extension not supported"),
                "login": smtplib.SMTPAuthenticationError(535, b"API key invalida"),
                "enviar": smtplib.SMTPRecipientsRefused({PARA: (550, b"no")}),
            }
            raise excepciones[paso]

    def __enter__(self) -> SmtpFalso:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.pasos.append("quit")

    def ehlo(self) -> None:
        self.pasos.append("ehlo")

    def starttls(self, context: Any) -> None:
        self._fallar("starttls")
        assert context.verify_mode is not None and context.check_hostname
        self.pasos.append("starttls")

    def login(self, usuario: str, clave: str) -> None:
        self._fallar("login")
        self.pasos.append("login")
        self.login_con = (usuario, clave)

    def send_message(self, mensaje: email.message.EmailMessage) -> None:
        self._fallar("enviar")
        self.pasos.append("enviar")
        # Como viaja por la red: bytes, y de vuelta a un mensaje.
        self.mensajes.append(
            email.message_from_bytes(mensaje.as_bytes(), policy=policy.default)  # type: ignore[arg-type]
        )


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> type[SmtpFalso]:
    SmtpFalso.instancias = []
    SmtpFalso.falla_en = None
    monkeypatch.setattr(adaptadores.smtplib, "SMTP", SmtpFalso)
    return SmtpFalso


def _resend(**cambios: Any) -> CorreoSmtp:
    datos: dict[str, Any] = {
        "host": "smtp.resend.com",
        "puerto": 2587,
        "usuario": "resend",
        "clave": "re_clave",
        "remitente": "no-responder@vectorhrtech.com",
    }
    datos.update(cambios)
    return CorreoSmtp(**datos)


async def test_resend_va_por_2587_con_starttls_antes_del_login(smtp: type[SmtpFalso]) -> None:
    correo = resumen(PARA, [diagnostico()], 0)
    assert correo is not None

    await _resend().enviar(correo)

    (conexion,) = smtp.instancias
    assert conexion.conexion[:2] == ("smtp.resend.com", 2587)
    assert conexion.pasos == ["ehlo", "starttls", "ehlo", "login", "enviar", "quit"]
    assert conexion.login_con == ("resend", "re_clave")
    (mensaje,) = conexion.mensajes
    assert mensaje["From"] == "no-responder@vectorhrtech.com"
    assert mensaje["To"] == PARA
    assert mensaje["Subject"] == "Nuevo diagnóstico: Andes Logística"
    assert mensaje.get_content_type() == "text/plain"
    assert "Horas recuperables al mes: 67.6" in mensaje.get_content()
    assert mensaje["Message-ID"].endswith("@vectorhrtech.com>")


async def test_ningun_dato_del_prospecto_va_en_las_cabeceras(smtp: type[SmtpFalso]) -> None:
    d = diagnostico(correo="mariana@andes.test", nombre="Mariana Ruiz")
    correo = resumen(PARA, [d, diagnostico()], 0)
    assert correo is not None

    await _resend().enviar(correo)

    (mensaje,) = smtp.instancias[0].mensajes
    cabeceras = "\n".join(f"{k}: {v}" for k, v in mensaje.items())
    assert "mariana@andes.test" not in cabeceras
    assert "Mariana" not in cabeceras
    assert "Andes" not in cabeceras


async def test_mailpit_sin_tls_ni_usuario(smtp: type[SmtpFalso]) -> None:
    await _resend(host="mailpit", puerto=1025, usuario="", starttls=False).enviar(
        CorreoSaliente(para=PARA, asunto="Nuevos diagnósticos: 1", cuerpo="hola\n")
    )
    assert smtp.instancias[0].pasos == ["ehlo", "enviar", "quit"]


@pytest.mark.parametrize("paso", ["conectar", "starttls", "login", "enviar"])
async def test_cualquier_fallo_del_smtp_es_correo_no_enviado(
    smtp: type[SmtpFalso], paso: str
) -> None:
    smtp.falla_en = paso
    with pytest.raises(CorreoNoEnviadoError):
        await _resend().enviar(CorreoSaliente(para=PARA, asunto="Asunto", cuerpo="hola\n"))


def _turnstile(respuesta: httpx.Response | Exception, enviados: list[dict[str, str]]):
    def responder(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == VERIFICAR_TURNSTILE
        enviados.append(dict(httpx.QueryParams(request.content.decode())))
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    return httpx.AsyncClient(transport=httpx.MockTransport(responder))


async def test_turnstile_manda_secreto_token_e_ip() -> None:
    enviados: list[dict[str, str]] = []
    async with _turnstile(httpx.Response(200, json={"success": True}), enviados) as http:
        assert await TurnstileCloudflare("secreto", http).verificar("tok", "203.0.113.7")
    assert enviados == [{"secret": "secreto", "response": "tok", "remoteip": "203.0.113.7"}]


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"success": False, "error-codes": ["timeout-or-duplicate"]},
        {"success": False, "error-codes": ["invalid-input-response"]},
        {"success": "true"},
    ],
)
async def test_turnstile_rechaza(cuerpo: dict[str, Any]) -> None:
    async with _turnstile(httpx.Response(200, content=json.dumps(cuerpo)), []) as http:
        assert not await TurnstileCloudflare("secreto", http).verificar("tok", None)


async def test_sin_token_ni_se_pregunta() -> None:
    enviados: list[dict[str, str]] = []
    async with _turnstile(httpx.Response(200, json={"success": True}), enviados) as http:
        assert not await TurnstileCloudflare("secreto", http).verificar(None, None)
    assert enviados == []


@pytest.mark.parametrize(
    "respuesta",
    [
        httpx.ConnectError("sin red"),
        httpx.Response(503),
        httpx.Response(429),
        httpx.Response(200, content=b"<html>"),
        httpx.Response(200, json={"success": False, "error-codes": ["internal-error"]}),
    ],
)
async def test_si_turnstile_no_responde_bien_no_se_sabe(
    respuesta: httpx.Response | Exception,
) -> None:
    async with _turnstile(respuesta, []) as http:
        with pytest.raises(VerificadorNoDisponibleError):
            await TurnstileCloudflare("secreto", http).verificar("tok", None)
