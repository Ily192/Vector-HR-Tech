"""SQL del alta de empresas (plan gratis).

Corre con el rol dueño de la base, sin contexto de tenant: crea la empresa, que
todavía no tiene a nadie dentro, y lee `auth.users`, que ningún rol de la API ve.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_ESTADO_DE_LA_CUENTA = text(
    """
    select case
             when u.id is null then 'sin-cuenta'
             when u.email_confirmed_at is null then 'pendiente'
             else 'confirmada'
           end
      from (select 1) as uno
      left join auth.users u on lower(u.email) = :correo
    """
)

# Las dos filas en una sola sentencia. Si el slug ya existe, `on conflict` no
# inserta la empresa y, sin empresa, tampoco la invitación: no vuelve ninguna fila.
_CREAR_EMPRESA_CON_INVITACION = text(
    """
    with empresa as (
        insert into public.empresas (name, slug, plan, tamano_empleados)
        values (:nombre, :slug, 'gratis', :tamano)
        on conflict (slug) do nothing
        returning id
    )
    insert into public.invitations (empresa_id, email, role, token_hash)
    select id, :correo, cast(:rol as public.role_type), :token_hash from empresa
    returning empresa_id
    """
)

_DESHACER = text("delete from public.empresas where id = :empresa_id")


async def estado_de_la_cuenta(db: AsyncSession, correo: str) -> str:
    return str((await db.execute(_ESTADO_DE_LA_CUENTA, {"correo": correo})).scalar_one())


async def crear_empresa_con_invitacion(
    db: AsyncSession,
    *,
    nombre: str,
    slug: str,
    tamano: int | None,
    correo: str,
    rol: str,
    token_hash: str,
) -> UUID | None:
    resultado = await db.execute(
        _CREAR_EMPRESA_CON_INVITACION,
        {
            "nombre": nombre,
            "slug": slug,
            "tamano": tamano,
            "correo": correo,
            "rol": rol,
            "token_hash": token_hash,
        },
    )
    empresa_id = resultado.scalar_one_or_none()
    return UUID(str(empresa_id)) if empresa_id is not None else None


async def deshacer(db: AsyncSession, empresa_id: UUID) -> None:
    await db.execute(_DESHACER, {"empresa_id": empresa_id})
