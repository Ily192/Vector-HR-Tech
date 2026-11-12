"""SQL de las altas desde la web (`privado.altas_web`, migración 0018).

Corre con el rol dueño de la base, como el alta por la terminal: crea empresas que
todavía no tienen a nadie dentro y lee `auth.users`, que ningún rol de la API ve.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, TEXT
from sqlalchemy.ext.asyncio import AsyncSession

_RESERVAR = text(
    """
    insert into privado.altas_web (
        lead_id, correo, publica_para, cargo, web_empresa, linkedin, verificacion,
        pais, tamano, sector, contrataciones_mes, puestos, origen, utm_medium,
        utm_campaign, ip_hash
    ) values (
        :lead_id, :correo, :publica_para, :cargo, :web_empresa, :linkedin, :verificacion,
        :pais, :tamano, :sector, :contrataciones_mes, :puestos, :origen, :utm_medium,
        :utm_campaign, :ip_hash
    )
    on conflict (lead_id) do nothing
    returning id
    """
).bindparams(bindparam("puestos", type_=ARRAY(TEXT)))

_COMPLETAR = text(
    """
    update privado.altas_web
       set empresa_id = :empresa_id, resultado = :resultado
     where lead_id = :lead_id
    """
)

# Solo la reserva de un alta que no terminó: una completa no se borra.
_LIBERAR = text("delete from privado.altas_web where lead_id = :lead_id and resultado is null")

# Confirmó quien escribió el código: Auth pone `email_confirmed_at` al verificarlo.
_MARCAR_CONFIRMADAS = text(
    """
    update privado.altas_web a
       set confirmado_en = c.confirmado
      from (
            select p.empresa_id, min(u.email_confirmed_at) as confirmado
              from public.profiles p
              join auth.users u on u.id = p.id
             where u.email_confirmed_at is not null
             group by p.empresa_id
           ) c
     where a.empresa_id = c.empresa_id
       and a.confirmado_en is null
    """
)

# Las que nadie confirmó, con sus cuentas de Auth. Nunca una empresa con una cuenta
# confirmada (por ejemplo, alguien que entró con una invitación de Vector HR) ni con
# vacantes.
_PENDIENTES = text(
    """
    select a.empresa_id,
           coalesce(array_agg(p.id) filter (where p.id is not null), '{}') as usuarios
      from privado.altas_web a
      left join public.profiles p on p.empresa_id = a.empresa_id
     where a.resultado = 'empresa_creada'
       and a.confirmado_en is null
       and a.creado_en < :antes_de
       and a.empresa_id is not null
       and not exists (
            select 1
              from public.profiles p2
              join auth.users u on u.id = p2.id
             where p2.empresa_id = a.empresa_id
               and u.email_confirmed_at is not null
           )
       and not exists (select 1 from public.vacantes v where v.empresa_id = a.empresa_id)
     group by a.empresa_id
    """
)

_BORRAR_EMPRESA = text("delete from public.empresas where id = :empresa_id")


async def reservar(db: AsyncSession, datos: dict[str, object]) -> bool:
    return (await db.execute(_RESERVAR, datos)).scalar_one_or_none() is not None


async def completar(
    db: AsyncSession, *, lead_id: str, empresa_id: UUID | None, resultado: str
) -> None:
    await db.execute(
        _COMPLETAR, {"lead_id": lead_id, "empresa_id": empresa_id, "resultado": resultado}
    )


async def liberar(db: AsyncSession, lead_id: str) -> None:
    await db.execute(_LIBERAR, {"lead_id": lead_id})


async def marcar_confirmadas(db: AsyncSession) -> int:
    resultado = await db.execute(_MARCAR_CONFIRMADAS)
    return int(getattr(resultado, "rowcount", 0) or 0)


async def pendientes_desde(db: AsyncSession, antes_de: datetime) -> list[tuple[UUID, list[UUID]]]:
    filas = (await db.execute(_PENDIENTES, {"antes_de": antes_de})).all()
    return [
        (UUID(str(empresa_id)), [UUID(str(u)) for u in usuarios]) for empresa_id, usuarios in filas
    ]


async def borrar_empresa(db: AsyncSession, empresa_id: UUID) -> None:
    await db.execute(_BORRAR_EMPRESA, {"empresa_id": empresa_id})
