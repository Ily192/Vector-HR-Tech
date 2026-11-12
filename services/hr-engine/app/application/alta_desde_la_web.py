"""Casos de uso del alta desde la web: registrarse con un código y limpiar lo que no se usó.

`DarDeAltaDesdeLaWeb` es lo que corre `POST /alta/plan-gratis`: la empresa queda
creada en el momento y la persona entra al panel escribiendo el código que le llega
al correo, sin invitación manual. `LimpiarAltasSinConfirmar` corre una vez al día y
borra las empresas cuyo dueño nunca escribió su código.

Orquestan el dominio (`domain/alta.py`, `domain/alta_web.py`) por los puertos; los
adaptadores están en `infrastructure/altas.py` e `infrastructure/altas_web.py`.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.application.dar_de_alta_empresa import crear_con_slug_libre
from app.domain.alta import hash_del_token, nuevo_token
from app.domain.alta_web import SolicitudDeAltaWeb, url_de_verificacion
from app.domain.puertos import (
    CodigoReenviadoMuyProntoError,
    LimitadorDeAltas,
    RepositorioDeAltas,
    RepositorioDeAltasWeb,
    ServicioDeCodigos,
)

#: Días que tiene quien se registró para escribir su código antes de que se borre todo.
DIAS_PARA_CONFIRMAR = 7


@dataclass(frozen=True)
class RespuestaDelAlta:
    """Lo que ve la web. Igual exista o no la cuenta: no revela quién usa el panel."""

    verificar_url: str
    estado: str = "codigo_enviado"


class DarDeAltaDesdeLaWeb:
    """Da de alta la empresa del registro de la web, o manda un código si ya tiene cuenta.

    - Un `lead_id` que ya llegó no crea ni manda nada: la web reintentó.
    - Con cuenta (confirmada o sin confirmar) solo sale un código para entrar.
    - Sin cuenta, la empresa y su invitación se guardan antes del correo: al crear la
      cuenta, `handle_new_user` (0003) tiene que encontrar la invitación por su token.
      Si el correo no sale, se deshace todo y la web puede reintentar.
    """

    def __init__(
        self,
        repositorio: RepositorioDeAltas,
        altas_web: RepositorioDeAltasWeb,
        codigos: ServicioDeCodigos,
        limitador: LimitadorDeAltas,
        url_del_panel: str,
        sufijo: Callable[[], str] = lambda: secrets.token_hex(2),
    ) -> None:
        self._repositorio = repositorio
        self._altas_web = altas_web
        self._codigos = codigos
        self._limitador = limitador
        self._url_del_panel = url_del_panel
        self._sufijo = sufijo

    async def ejecutar(
        self, solicitud: SolicitudDeAltaWeb, ip_hash: str | None
    ) -> RespuestaDelAlta:
        respuesta = RespuestaDelAlta(url_de_verificacion(self._url_del_panel, solicitud.correo))
        # El límite va antes de la reserva y después de saber si es un reintento: un
        # reintento de la web no gasta cupo, pero sí lo gasta cada registro nuevo.
        if not await self._altas_web.reservar(solicitud, ip_hash):
            return respuesta
        try:
            await self._limitador.consumir(ip_hash, solicitud.correo)
            await self._dar_de_alta_o_mandar_codigo(solicitud)
        except BaseException:
            await self._altas_web.liberar(solicitud.lead_id)
            raise
        return respuesta

    async def _dar_de_alta_o_mandar_codigo(self, solicitud: SolicitudDeAltaWeb) -> None:
        estado = await self._repositorio.estado_de_la_cuenta(solicitud.correo)
        if estado != "sin-cuenta":
            # El código de hace menos de un minuto sigue sirviendo.
            with suppress(CodigoReenviadoMuyProntoError):
                await self._codigos.mandar_codigo_de_entrada(solicitud.correo, solicitud.ip)
            await self._altas_web.completar(solicitud.lead_id, None, "cuenta_existente")
            return

        token = nuevo_token()
        empresa_id, _ = await crear_con_slug_libre(
            self._repositorio, solicitud.alta, hash_del_token(token), self._sufijo
        )
        try:
            await self._codigos.mandar_codigo_de_alta(
                solicitud.correo, token, solicitud.alta.nombre, solicitud.ip
            )
        except BaseException:
            await self._repositorio.deshacer(empresa_id)
            raise
        await self._altas_web.completar(solicitud.lead_id, empresa_id, "empresa_creada")


@dataclass(frozen=True)
class ResultadoDeLaLimpieza:
    confirmadas: int = 0
    borradas: int = 0
    con_error: int = 0


class LimpiarAltasSinConfirmar:
    """Borra las empresas que se registraron por la web y nunca confirmaron el código.

    Primero marca las confirmadas, después borra la cuenta de Auth y por último la
    empresa: si Auth no responde, la empresa espera al día siguiente y no queda una
    cuenta sin empresa. Nunca toca una empresa con alguien que ya confirmó su correo.
    """

    def __init__(
        self,
        altas_web: RepositorioDeAltasWeb,
        codigos: ServicioDeCodigos,
        dias: int = DIAS_PARA_CONFIRMAR,
        ahora: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._altas_web = altas_web
        self._codigos = codigos
        self._dias = dias
        self._ahora = ahora

    async def ejecutar(self) -> ResultadoDeLaLimpieza:
        confirmadas = await self._altas_web.marcar_confirmadas()
        borradas = con_error = 0
        limite = self._ahora() - timedelta(days=self._dias)
        for pendiente in await self._altas_web.pendientes_desde(limite):
            try:
                for usuario in pendiente.usuarios:
                    await self._codigos.borrar_usuario(usuario)
            except Exception:
                con_error += 1
                continue
            await self._altas_web.borrar_empresa(pendiente.empresa_id)
            borradas += 1
        return ResultadoDeLaLimpieza(
            confirmadas=confirmadas, borradas=borradas, con_error=con_error
        )
