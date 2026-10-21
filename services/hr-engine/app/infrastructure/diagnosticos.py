"""Adaptadores del aviso de los diagnósticos gratuitos (migración 0017).

El SQL, Cloudflare Turnstile y el SMTP de Resend. Traducen y nada más: qué se
avisa, cuándo se descarta y qué dice el correo son del dominio y del caso de uso.
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.diagnostico import MAX_INTENTOS_AVISO, CorreoSaliente, Diagnostico
from app.domain.puertos import CorreoNoEnviadoError, VerificadorNoDisponibleError
from app.monitoring import logger
from app.repositories import diagnosticos as diagnosticos_repo

#: Turnstile: "POST https://challenges.cloudflare.com/turnstile/v0/siteverify" con
#: `secret`, `response` y `remoteip`. El mismo que usa el career site.
VERIFICAR_TURNSTILE = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


class SqlRepositorioDeDiagnosticos:
    """`RepositorioDeDiagnosticos` sobre la sesión del worker (rol dueño).

    Todo el barrido es una transacción: los reclamados quedan bloqueados (`for update
    skip locked`) hasta `confirmar()`.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def reclamar(self, limite: int) -> list[Diagnostico]:
        return [
            Diagnostico(
                id=f.id,
                creado_en=f.creado_en,
                nombre=f.nombre,
                empresa=f.empresa,
                correo=f.correo,
                origen=f.origen,
                utm_medium=f.utm_medium,
                utm_campaign=f.utm_campaign,
                horas_recuperables_mes=float(f.horas_recuperables_mes),
                resultado=f.resultado if isinstance(f.resultado, dict) else {},
                ip=f.ip,
                turnstile_token=f.turnstile_token,
                verificado=f.verificado,
                sin_fines_comerciales=f.sin_fines_comerciales,
            )
            for f in await diagnosticos_repo.reclamar(
                self._db, limite=limite, max_intentos=MAX_INTENTOS_AVISO
            )
        ]

    async def avisados_hoy(self) -> int:
        return await diagnosticos_repo.avisados_hoy(self._db)

    async def marcar_verificado(self, diagnostico: Diagnostico) -> None:
        await diagnosticos_repo.marcar_verificado(self._db, diagnostico_id=diagnostico.id)

    async def descartar(self, diagnostico: Diagnostico) -> None:
        await diagnosticos_repo.descartar(self._db, diagnostico_id=diagnostico.id)

    async def marcar_avisados(self, diagnosticos: list[Diagnostico]) -> None:
        await diagnosticos_repo.marcar_avisados(self._db, ids=[d.id for d in diagnosticos])

    async def sumar_intento(self, diagnosticos: list[Diagnostico]) -> None:
        await diagnosticos_repo.sumar_intento(self._db, ids=[d.id for d in diagnosticos])

    async def confirmar(self) -> None:
        await self._db.commit()


class TurnstileCloudflare:
    """`VerificadorHumano` con la clave secreta de Turnstile. El token vale una sola vez."""

    def __init__(self, secreto: str, http: httpx.AsyncClient) -> None:
        self._secreto = secreto
        self._http = http

    async def verificar(self, token: str | None, ip: str | None) -> bool:
        if not token:
            return False
        cuerpo = {"secret": self._secreto, "response": token}
        if ip:
            cuerpo["remoteip"] = ip
        try:
            respuesta = await self._http.post(VERIFICAR_TURNSTILE, data=cuerpo)
        except httpx.HTTPError as exc:
            raise VerificadorNoDisponibleError(
                f"Turnstile no responde: {type(exc).__name__}"
            ) from exc
        if respuesta.status_code >= 500 or respuesta.status_code == 429:
            raise VerificadorNoDisponibleError(f"Turnstile respondió {respuesta.status_code}")
        try:
            datos = respuesta.json()
        except ValueError as exc:
            raise VerificadorNoDisponibleError("Turnstile respondió algo que no es JSON") from exc
        if not isinstance(datos, dict):
            raise VerificadorNoDisponibleError("Turnstile respondió algo que no es un objeto")
        if datos.get("success") is not True:
            # Solo los códigos de Cloudflare: el token no se registra.
            logger.info("diagnosticos.turnstile_rechazado", codigos=datos.get("error-codes"))
            if "internal-error" in (datos.get("error-codes") or []):
                raise VerificadorNoDisponibleError("Turnstile: internal-error")
            return False
        return True


class CorreoSmtp:
    """`ServicioDeCorreo` por SMTP con smtplib. Resend: smtp.resend.com, 2587 y STARTTLS,
    porque DigitalOcean bloquea 25, 465 y 587; usuario `resend` y la API key de clave.

    `starttls=False` solo para Mailpit en la prueba local: sin TLS la clave viajaría en
    claro, así que en producción se exige y se valida el certificado.
    """

    def __init__(
        self,
        *,
        host: str,
        puerto: int,
        usuario: str,
        clave: str,
        remitente: str,
        starttls: bool = True,
        timeout_s: float = 30.0,
    ) -> None:
        self._host = host
        self._puerto = puerto
        self._usuario = usuario
        self._clave = clave
        self._remitente = remitente
        self._starttls = starttls
        self._timeout_s = timeout_s

    def _mensaje(self, correo: CorreoSaliente) -> EmailMessage:
        mensaje = EmailMessage()
        mensaje["From"] = self._remitente
        mensaje["To"] = correo.para
        # El asunto ya viene en una línea (`domain/diagnostico.py`); EmailMessage además
        # rechaza un salto de línea en una cabecera.
        mensaje["Subject"] = correo.asunto
        mensaje["Date"] = formatdate(localtime=False)
        mensaje["Message-ID"] = make_msgid(domain=self._remitente.rpartition("@")[2] or None)
        mensaje.set_content(correo.cuerpo, subtype="plain", charset="utf-8")
        return mensaje

    def _enviar(self, mensaje: EmailMessage) -> None:
        with smtplib.SMTP(self._host, self._puerto, timeout=self._timeout_s) as smtp:
            smtp.ehlo()
            if self._starttls:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if self._usuario:
                smtp.login(self._usuario, self._clave)
            smtp.send_message(mensaje)

    async def enviar(self, correo: CorreoSaliente) -> None:
        mensaje = self._mensaje(correo)
        try:
            # smtplib bloquea: va en un hilo para no detener el event loop de la tarea.
            await asyncio.to_thread(self._enviar, mensaje)
        except (smtplib.SMTPException, OSError) as exc:
            raise CorreoNoEnviadoError(
                f"el SMTP no aceptó el correo: {type(exc).__name__}"
            ) from exc
