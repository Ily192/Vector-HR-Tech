"""Adaptadores del alta desde la web: el SQL, el código de Supabase Auth y los topes.

Traducen y nada más. Qué se valida, en qué orden y cuándo se deshace es del dominio
(`domain/alta_web.py`) y del caso de uso (`application/alta_desde_la_web.py`).
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import datetime
from uuid import UUID

import httpx
from limits import RateLimitItem, parse
from limits.storage import storage_from_string
from limits.strategies import MovingWindowRateLimiter
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.alta_web import SolicitudDeAltaWeb
from app.domain.puertos import (
    AltaPendiente,
    CodigoNoEnviadoError,
    CodigoReenviadoMuyProntoError,
    LimiteDeAltasError,
    ResultadoDeAltaWeb,
)
from app.infrastructure.altas import VERSION_DE_LA_API_DE_AUTH, codigo_de_error
from app.monitoring import logger
from app.repositories import altas_web as altas_web_repo

#: La cabecera con la IP del visitante que Auth usa para sus topes por IP
#: (GOTRUE_RATE_LIMIT_HEADER en infra/vps/compose.yml).
CABECERA_DE_LA_IP = "CF-Connecting-IP"
#: Si Auth corta por IP, cuánto se le pide a la web que espere.
ESPERA_SI_AUTH_CORTA_S = 600


class SqlRepositorioDeAltasWeb:
    """`RepositorioDeAltasWeb` sobre una sesión con el rol dueño. Confirma cada escritura:
    la reserva tiene que estar guardada antes de crear nada."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def reservar(self, solicitud: SolicitudDeAltaWeb, ip_hash: str | None) -> bool:
        reservada = await altas_web_repo.reservar(
            self._db,
            {
                "lead_id": solicitud.lead_id,
                "correo": solicitud.correo,
                "publica_para": solicitud.publica_para,
                "cargo": solicitud.cargo,
                "web_empresa": solicitud.web_empresa,
                "linkedin": solicitud.linkedin,
                "verificacion": solicitud.verificacion,
                "pais": solicitud.pais,
                "tamano": solicitud.tamano,
                "sector": solicitud.sector,
                "contrataciones_mes": solicitud.contrataciones_mes,
                "puestos": list(solicitud.puestos),
                "origen": solicitud.origen,
                "utm_medium": solicitud.utm_medium,
                "utm_campaign": solicitud.utm_campaign,
                "ip_hash": ip_hash,
            },
        )
        await self._db.commit()
        return reservada

    async def completar(
        self, lead_id: str, empresa_id: UUID | None, resultado: ResultadoDeAltaWeb
    ) -> None:
        await altas_web_repo.completar(
            self._db, lead_id=lead_id, empresa_id=empresa_id, resultado=resultado
        )
        await self._db.commit()

    async def liberar(self, lead_id: str) -> None:
        await self._db.rollback()
        await altas_web_repo.liberar(self._db, lead_id)
        await self._db.commit()

    async def marcar_confirmadas(self) -> int:
        cuantas = await altas_web_repo.marcar_confirmadas(self._db)
        await self._db.commit()
        return cuantas

    async def pendientes_desde(self, antes_de: datetime) -> list[AltaPendiente]:
        filas = await altas_web_repo.pendientes_desde(self._db, antes_de)
        return [AltaPendiente(empresa_id=e, usuarios=tuple(u)) for e, u in filas]

    async def borrar_empresa(self, empresa_id: UUID) -> None:
        await altas_web_repo.borrar_empresa(self._db, empresa_id)
        await self._db.commit()


class CodigosSupabase:
    """`ServicioDeCodigos` sobre `POST /auth/v1/otp` y la API de administración.

    `/otp` con un correo nuevo y `create_user: true` crea la cuenta con `data` como
    `raw_user_meta_data` y, con GOTRUE_MAILER_AUTOCONFIRM=false, manda el correo de
    confirmación con `{{ .Token }}`. A una cuenta que ya existe le manda el de magic
    link, también con el código (supabase/auth v2.197.0: internal/api/otp.go,
    magic_link.go y signup.go). La cuenta queda sin confirmar hasta que la persona
    escribe el código.
    """

    def __init__(self, url: str, clave: str, http: httpx.AsyncClient) -> None:
        self._url = url.rstrip("/")
        self._clave = clave
        self._http = http

    def _cabeceras(self, ip: str | None = None) -> dict[str, str]:
        cabeceras = {"apikey": self._clave, "X-Supabase-Api-Version": VERSION_DE_LA_API_DE_AUTH}
        if self._clave.startswith("eyJ"):
            cabeceras["Authorization"] = f"Bearer {self._clave}"
        if ip:
            # Desde la red interna no llega la cabecera de Cloudflare y Auth no aplicaría
            # su tope por IP: se le pasa la del visitante.
            cabeceras[CABECERA_DE_LA_IP] = ip
        return cabeceras

    async def mandar_codigo_de_alta(
        self, correo: str, token: str, nombre: str, ip: str | None
    ) -> None:
        cuerpo = {
            "email": correo,
            "create_user": True,
            "data": {"invite_token": token, "full_name": nombre},
        }
        # A una cuenta nueva no le aplica la espera de un minuto entre correos: si Auth
        # dice que se pasó de correos, es su tope por hora y el código no salió.
        await self._otp(cuerpo, ip, muy_pronto_es_error=True)

    async def mandar_codigo_de_entrada(self, correo: str, ip: str | None) -> None:
        await self._otp({"email": correo, "create_user": False}, ip, muy_pronto_es_error=False)

    async def _otp(
        self, cuerpo: dict[str, object], ip: str | None, *, muy_pronto_es_error: bool
    ) -> None:
        try:
            respuesta = await self._http.post(
                f"{self._url}/auth/v1/otp", headers=self._cabeceras(ip), json=cuerpo
            )
        except httpx.HTTPError as exc:
            raise CodigoNoEnviadoError(f"Auth no responde: {type(exc).__name__}") from exc
        if respuesta.status_code == 200:
            return
        codigo = codigo_de_error(respuesta)
        if codigo == "over_email_send_rate_limit" and not muy_pronto_es_error:
            raise CodigoReenviadoMuyProntoError("ya salió un código hace menos de un minuto")
        if codigo == "over_request_rate_limit":
            raise LimiteDeAltasError(ESPERA_SI_AUTH_CORTA_S)
        raise CodigoNoEnviadoError(f"Auth respondió {respuesta.status_code} ({codigo})")

    async def borrar_usuario(self, usuario_id: UUID) -> None:
        try:
            respuesta = await self._http.delete(
                f"{self._url}/auth/v1/admin/users/{usuario_id}", headers=self._cabeceras()
            )
        except httpx.HTTPError as exc:
            raise CodigoNoEnviadoError(f"Auth no responde: {type(exc).__name__}") from exc
        # 404: ya no estaba, que es lo que se quería.
        if respuesta.status_code not in (200, 204, 404):
            raise CodigoNoEnviadoError(
                f"Auth no borró la cuenta: {respuesta.status_code} ({codigo_de_error(respuesta)})"
            )


class LimitadorConLimits:
    """`LimitadorDeAltas` con `limits` (la misma biblioteca de slowapi) y ventana móvil.

    En producción el almacén es el Redis del stack (RATE_LIMIT_STORAGE_URI), que comparten
    todos los procesos de la API. El correo se guarda con hash: en Redis no queda ninguno.
    """

    def __init__(self, storage_uri: str, por_ip: str, por_correo: str) -> None:
        self._limitador = MovingWindowRateLimiter(storage_from_string(storage_uri))
        self._por_ip: RateLimitItem = parse(por_ip)
        self._por_correo: RateLimitItem = parse(por_correo)

    async def consumir(self, ip_hash: str | None, correo: str) -> None:
        try:
            await asyncio.to_thread(self._consumir, ip_hash, correo)
        except LimiteDeAltasError:
            raise
        except Exception as exc:
            # Sin Redis no se corta el alta: quedan Turnstile en la web y el tope por IP
            # de Auth. Se avisa en los logs.
            logger.warning("alta_web.limitador_caido", error=type(exc).__name__)

    def _consumir(self, ip_hash: str | None, correo: str) -> None:
        claves: list[tuple[RateLimitItem, str]] = [
            (self._por_correo, hashlib.sha256(correo.encode()).hexdigest())
        ]
        if ip_hash:
            claves.append((self._por_ip, ip_hash))
        for limite, clave in claves:
            if not self._limitador.test(limite, "alta-plan-gratis", clave):
                reinicio = self._limitador.get_window_stats(
                    limite, "alta-plan-gratis", clave
                ).reset_time
                raise LimiteDeAltasError(max(1, int(reinicio - time.time()) + 1))
        for limite, clave in claves:
            self._limitador.hit(limite, "alta-plan-gratis", clave)
