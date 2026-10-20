"""Adaptadores del alta de empresas: el SQL y la API de administración de Supabase Auth.

Traducen y nada más. Qué se valida, en qué orden y cuándo se deshace es del
dominio (`domain/alta.py`) y del caso de uso (`application/dar_de_alta_empresa.py`).
"""

from __future__ import annotations

import json
from typing import cast
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.alta import SolicitudDeAlta
from app.domain.puertos import CuentaYaExisteError, EstadoDeCuenta, InvitacionNoEnviadaError
from app.repositories import altas as altas_repo

#: Con esta versión, Auth responde los errores como `{"code", "message"}`.
VERSION_DE_LA_API_DE_AUTH = "2024-01-01"


class SqlRepositorioDeAltas:
    """`RepositorioDeAltas` sobre una sesión con el rol dueño. Confirma cada escritura:
    la invitación tiene que estar guardada antes de que Auth cree la cuenta."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def estado_de_la_cuenta(self, correo: str) -> EstadoDeCuenta:
        return cast(EstadoDeCuenta, await altas_repo.estado_de_la_cuenta(self._db, correo))

    async def crear_empresa_con_invitacion(
        self, solicitud: SolicitudDeAlta, slug: str, token_hash: str
    ) -> UUID | None:
        empresa_id = await altas_repo.crear_empresa_con_invitacion(
            self._db,
            nombre=solicitud.empresa,
            slug=slug,
            tamano=solicitud.tamano,
            correo=solicitud.correo,
            rol=solicitud.rol,
            token_hash=token_hash,
        )
        await self._db.commit()
        return empresa_id

    async def deshacer(self, empresa_id: UUID) -> None:
        await altas_repo.deshacer(self._db, empresa_id)
        await self._db.commit()


class InvitacionesSupabase:
    """`ServicioDeInvitaciones` sobre `POST /auth/v1/invite` con la clave secreta.

    Es la llamada de `auth.admin.inviteUserByEmail(email, { data, redirectTo })`:
    el cuerpo lleva el correo y el metadata, y `redirect_to` va en la query. El
    enlace del correo vuelve al panel con la sesión (flujo implícito).
    """

    def __init__(self, url: str, clave: str, url_del_panel: str, http: httpx.AsyncClient) -> None:
        self._url = url.rstrip("/")
        self._clave = clave
        self._url_del_panel = url_del_panel
        self._http = http

    def _cabeceras(self) -> dict[str, str]:
        # Igual que `AlmacenSupabase`: la clave nueva va en `apikey`; la `service_role`
        # legada es un JWT y también va como Bearer.
        cabeceras = {"apikey": self._clave, "X-Supabase-Api-Version": VERSION_DE_LA_API_DE_AUTH}
        if self._clave.startswith("eyJ"):
            cabeceras["Authorization"] = f"Bearer {self._clave}"
        return cabeceras

    async def invitar(self, correo: str, token: str, nombre: str) -> None:
        await self._mandar(
            correo, {"email": correo, "data": {"invite_token": token, "full_name": nombre}}
        )

    async def reenviar(self, correo: str) -> None:
        # A una cuenta sin confirmar, Auth le manda otra invitación sin crear nada.
        await self._mandar(correo, {"email": correo})

    async def _mandar(self, correo: str, cuerpo: dict[str, object]) -> None:
        try:
            respuesta = await self._http.post(
                f"{self._url}/auth/v1/invite",
                params={"redirect_to": self._url_del_panel},
                headers=self._cabeceras(),
                json=cuerpo,
            )
        except httpx.HTTPError as exc:
            raise InvitacionNoEnviadaError(f"Auth no responde: {type(exc).__name__}") from exc
        if respuesta.status_code == 200:
            return
        codigo = _codigo_de_error(respuesta)
        if codigo == "email_exists":
            raise CuentaYaExisteError(f"{correo} ya tiene cuenta en el panel")
        raise InvitacionNoEnviadaError(f"Auth respondió {respuesta.status_code} ({codigo})")


def _codigo_de_error(respuesta: httpx.Response) -> str:
    try:
        cuerpo = respuesta.json()
    except json.JSONDecodeError:
        return "sin código"
    if not isinstance(cuerpo, dict):
        return "sin código"
    # Sin la cabecera de versión, `code` es el estado HTTP y el texto va en `error_code`.
    codigo = cuerpo.get("error_code") or cuerpo.get("code")
    return codigo if isinstance(codigo, str) else "sin código"
