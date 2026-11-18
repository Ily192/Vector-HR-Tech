"""Adaptadores del área de admin del panel (ADR-022, enmienda del 2026-11-17).

- `SesionesSupabase`: de quién es el token del panel, con `GET /auth/v1/user` de Auth.
  Es la forma que documenta Supabase de validar una sesión desde un servidor
  (`auth.getUser(jwt)`): Auth revisa la firma, el vencimiento y que la cuenta exista.
- `SqlResumenDeLaPlataforma`: los conteos del tablero, sobre `app/repositories/admin.py`.
"""

from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.admin import AuthNoDisponibleError, ResumenDeLaPlataforma, UsuarioDeAuth
from app.domain.moderacion import EstadoDeModeracion
from app.monitoring import logger
from app.repositories import admin as admin_repo

#: Lo que Auth contesta a un token que no sirve: sin token (401), vencido o con otra
#: firma (403 `bad_jwt`) o de una cuenta que ya no existe (403/404 `user_not_found`).
_TOKEN_QUE_NO_SIRVE = frozenset({401, 403, 404})


class SesionesSupabase:
    """`SesionesDeAuth` sobre `GET /auth/v1/user`, con la clave secreta como `apikey`.

    El gateway (Envoy en el VPS) pide la `apikey`; Auth lee la sesión del `Authorization`.
    En el VPS la URL es la interna (`http://api-gw:8000`): no sale a Cloudflare.
    """

    def __init__(self, url: str, clave: str, http: httpx.AsyncClient) -> None:
        self._url = url.rstrip("/")
        self._clave = clave
        self._http = http

    async def usuario(self, token: str) -> UsuarioDeAuth | None:
        try:
            respuesta = await self._http.get(
                f"{self._url}/auth/v1/user",
                headers={"apikey": self._clave, "Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError as exc:
            raise AuthNoDisponibleError(type(exc).__name__) from exc
        if respuesta.status_code in _TOKEN_QUE_NO_SIRVE:
            # Ni el token ni el cuerpo van al log: solo el código, por si es la apikey.
            logger.info("admin.sesion_invalida", status=respuesta.status_code)
            return None
        if respuesta.status_code != 200:
            raise AuthNoDisponibleError(f"Auth respondió {respuesta.status_code}")
        try:
            datos = respuesta.json()
        except ValueError as exc:
            raise AuthNoDisponibleError("Auth no respondió JSON") from exc
        correo = datos.get("email") if isinstance(datos, dict) else None
        if not isinstance(correo, str) or not correo.strip():
            return None
        return UsuarioDeAuth(correo=correo, confirmado=bool(datos.get("email_confirmed_at")))


class SqlResumenDeLaPlataforma:
    """`RepositorioDelResumen` sobre la sesión del hr-engine (rol dueño). Solo lee."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def resumen(self) -> ResumenDeLaPlataforma:
        c = await admin_repo.conteos(self._db)
        por_estado = {
            EstadoDeModeracion(f.estado): int(f.n)
            for f in await admin_repo.por_moderacion(self._db)
        }
        return ResumenDeLaPlataforma(
            empresas=int(c.empresas),
            empresas_verificadas=int(c.empresas_verificadas),
            altas_web_confirmadas=int(c.altas_web_confirmadas),
            altas_ultimos_7_dias=int(c.altas_ultimos_7_dias),
            vacantes_por_moderacion={e: por_estado.get(e, 0) for e in EstadoDeModeracion},
            vacantes_abiertas=int(c.vacantes_abiertas),
            vacantes_cerradas=int(c.vacantes_cerradas),
            aplicaciones=int(c.aplicaciones),
            aplicaciones_ultimos_7_dias=int(c.aplicaciones_ultimos_7_dias),
        )
