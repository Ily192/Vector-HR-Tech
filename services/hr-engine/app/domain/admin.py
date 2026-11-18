"""El área de admin del panel (ADR-022, enmienda del 2026-11-17).

Ilyra ve las métricas de la plataforma y resuelve la cola de revisión desde el panel
(`/admin`), también en el teléfono. Quién entra lo decide una lista de correos del
hr-engine (`ADMIN_CORREOS`), no `platform_admins` (0004): ese rol salta la RLS de todas
las empresas, y para contar filas y aprobar vacantes basta con el hr-engine, que ya lo
hace con el rol dueño.

La sesión es la misma del panel: el hr-engine le pregunta a Auth de quién es el token
(`SesionesDeAuth`) y decide aquí si esa cuenta entra.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Protocol

from app.domain.moderacion import EstadoDeModeracion


@dataclass(frozen=True, slots=True)
class UsuarioDeAuth:
    """Lo que Auth dice de la sesión que trae el panel."""

    correo: str
    #: Escribió el código que le llegó al correo (`email_confirmed_at`).
    confirmado: bool


def es_admin(usuario: UsuarioDeAuth, permitidos: Collection[str]) -> bool:
    """Entra con el correo confirmado y en la lista. `permitidos` va en minúsculas."""
    return usuario.confirmado and usuario.correo.strip().lower() in permitidos


class AuthNoDisponibleError(RuntimeError):
    """Auth no contestó o contestó algo inesperado: no se sabe de quién es el token."""


class SesionesDeAuth(Protocol):
    async def usuario(self, token: str) -> UsuarioDeAuth | None:
        """La cuenta del token, o `None` si el token no sirve (vencido, falso o de una
        cuenta borrada). Lanza `AuthNoDisponibleError` si Auth no responde."""
        ...


@dataclass(frozen=True, slots=True)
class ResumenDeLaPlataforma:
    """Los conteos del tablero de admin. Solo números: nada de empresas ni candidatos."""

    empresas: int
    empresas_verificadas: int
    #: Altas desde vectorhrtech.com/publicar-vacantes cuyo dueño escribió el código.
    altas_web_confirmadas: int
    #: Altas desde la web de los últimos 7 días, confirmadas o no.
    altas_ultimos_7_dias: int
    #: Vacantes abiertas por estado de la moderación (0019). Los cinco estados, con 0.
    vacantes_por_moderacion: Mapping[EstadoDeModeracion, int]
    vacantes_abiertas: int
    #: Cerradas o cubiertas: "eliminar" en el panel cierra la vacante.
    vacantes_cerradas: int
    aplicaciones: int
    aplicaciones_ultimos_7_dias: int


class RepositorioDelResumen(Protocol):
    async def resumen(self) -> ResumenDeLaPlataforma: ...


__all__ = [
    "AuthNoDisponibleError",
    "RepositorioDelResumen",
    "ResumenDeLaPlataforma",
    "SesionesDeAuth",
    "UsuarioDeAuth",
    "es_admin",
]
