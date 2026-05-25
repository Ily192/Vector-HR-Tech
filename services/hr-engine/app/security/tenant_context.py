"""Setea el contexto de tenant en la sesión Postgres para que RLS aplique.

Patrón (ADR-004): aunque los workers tienen acceso DB completo, propagamos
`empresa_id` + `role` del JWT/run-token a `request.jwt.claim.*` para que las
políticas RLS apliquen y se note inmediatamente cualquier tenant-leak.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

VALID_ROLES = frozenset({"Colaborador", "HR", "Director", "SuperAdmin", "cliente"})


async def set_tenant_context(
    db: AsyncSession,
    empresa_id: UUID | str,
    *,
    role: str = "HR",
) -> None:
    """Aplica `set local` para que duren solo en la transacción actual.

    Llamar SIEMPRE antes de cualquier query de dominio dentro del worker.
    """
    if role not in VALID_ROLES:
        raise ValueError(f"role inválido: {role}. Permitidos: {sorted(VALID_ROLES)}")
    empresa_str = str(UUID(str(empresa_id)))
    # `set local` aplica solo dentro de la transacción actual — seguro contra
    # leaks si el pool reutiliza la conexión para otro tenant.
    await db.execute(text("set local role authenticated"))
    await db.execute(
        text("select set_config('request.jwt.claim.empresa_id', :v, true)"),
        {"v": empresa_str},
    )
    await db.execute(
        text("select set_config('request.jwt.claim.role', :v, true)"),
        {"v": role},
    )


async def reset_tenant_context(db: AsyncSession) -> None:
    """Volver a DB owner (para tests / scripts admin)."""
    await db.execute(text("reset role"))
