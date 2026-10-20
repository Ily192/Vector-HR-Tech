"""Casos de uso del alta de empresas en el plan gratis: darla de alta e invitar a su HR.

Orquestan el dominio (`domain/alta.py`) por los puertos `RepositorioDeAltas` y
`ServicioDeInvitaciones`. No saben de SQL ni de la API de Auth: los adaptadores
están en `infrastructure/altas.py` y la entrada es `app/cli/alta_empresa.py`.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from app.domain.alta import SolicitudDeAlta, hash_del_token, nuevo_token, slug_de_empresa
from app.domain.puertos import CuentaYaExisteError, RepositorioDeAltas, ServicioDeInvitaciones

#: Intentos con sufijo cuando el slug limpio ya es de otra empresa.
INTENTOS_DE_SLUG = 3


@dataclass(frozen=True)
class ResultadoDelAlta:
    empresa_id: UUID
    slug: str


class DarDeAltaEmpresa:
    """Crea la empresa con su invitación de un solo uso y manda el correo.

    La empresa y la invitación se guardan juntas y antes del correo: al aceptar,
    Auth crea la cuenta y `handle_new_user` tiene que encontrar la invitación. Si
    el correo no sale, se deshace todo para poder repetir el alta tal cual.
    """

    def __init__(
        self,
        repositorio: RepositorioDeAltas,
        invitaciones: ServicioDeInvitaciones,
        sufijo: Callable[[], str] = lambda: secrets.token_hex(2),
    ) -> None:
        self._repositorio = repositorio
        self._invitaciones = invitaciones
        self._sufijo = sufijo

    async def ejecutar(self, solicitud: SolicitudDeAlta) -> ResultadoDelAlta:
        estado = await self._repositorio.estado_de_la_cuenta(solicitud.correo)
        if estado == "pendiente":
            raise CuentaYaExisteError(
                f"{solicitud.correo} ya tiene una invitación sin aceptar: reenvíala"
            )
        if estado == "confirmada":
            raise CuentaYaExisteError(f"{solicitud.correo} ya tiene cuenta en el panel")

        token = nuevo_token()
        slug = slug_de_empresa(solicitud.empresa)
        empresa_id = await self._repositorio.crear_empresa_con_invitacion(
            solicitud, slug, hash_del_token(token)
        )
        for _ in range(INTENTOS_DE_SLUG):
            if empresa_id is not None:
                break
            slug = slug_de_empresa(solicitud.empresa, self._sufijo())
            empresa_id = await self._repositorio.crear_empresa_con_invitacion(
                solicitud, slug, hash_del_token(token)
            )
        if empresa_id is None:
            raise RuntimeError(f"no hubo un slug libre para {solicitud.empresa!r}")

        try:
            await self._invitaciones.invitar(solicitud.correo, token, solicitud.nombre)
        except Exception:
            await self._repositorio.deshacer(empresa_id)
            raise
        return ResultadoDelAlta(empresa_id=empresa_id, slug=slug)


class ReenviarInvitacion:
    """Vuelve a mandar la invitación a quien todavía no entra: el enlace dura una hora.

    No crea nada: la cuenta y su empresa existen desde la primera invitación.
    """

    def __init__(
        self, repositorio: RepositorioDeAltas, invitaciones: ServicioDeInvitaciones
    ) -> None:
        self._repositorio = repositorio
        self._invitaciones = invitaciones

    async def ejecutar(self, correo: str) -> None:
        correo = correo.strip().lower()
        estado = await self._repositorio.estado_de_la_cuenta(correo)
        if estado == "sin-cuenta":
            raise LookupError(f"{correo} no tiene invitación: da de alta su empresa primero")
        if estado == "confirmada":
            raise CuentaYaExisteError(f"{correo} ya entró al panel; entra con su correo")
        await self._invitaciones.reenviar(correo)
