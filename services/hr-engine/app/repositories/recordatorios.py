"""SQL del recordatorio de postulados sin revisar (ADR-023, migración 0020).

Corre con la sesión del hr-engine con el rol dueño y sin contexto de tenant, como la
moderación: lee las postulaciones de todas las empresas y las tablas de `privado`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Sin revisar = llegó a una vacante abierta después de que la empresa abrió sus
# postulaciones y después de su último recordatorio. `row_number()` numera las de
# cada empresa por orden de llegada: la número `umbral + 1` es la que cruzó el umbral
# ("Returns the number of the current row within its partition, counting from 1",
# https://www.postgresql.org/docs/17/functions-window.html).
# Destinatarios: HR y Dirección con el correo confirmado en Auth, los que ven las
# postulaciones en el panel.
_CON_POSTULADOS_SIN_REVISAR = text(
    """
    with recordado as (
        select empresa_id, max(enviado_en) as recordado_en
          from privado.recordatorios_de_postulados
         group by empresa_id
    ),
    visto as (
        select empresa_id, max(vistas_en) as visto_en
          from privado.postulaciones_vistas
         group by empresa_id
    ),
    sin_revisar as (
        select a.empresa_id, a.vacante_id, v.title as titulo, a.applied_at,
               row_number() over (
                   partition by a.empresa_id order by a.applied_at, a.id
               ) as orden
          from public.applications a
          join public.vacantes v on v.id = a.vacante_id
          left join privado.postulaciones_vistas pv on pv.vacante_id = a.vacante_id
          left join recordado r on r.empresa_id = a.empresa_id
         where v.status = 'open'
           and a.applied_at > coalesce(pv.vistas_en, '-infinity'::timestamptz)
           and a.applied_at > coalesce(r.recordado_en, '-infinity'::timestamptz)
    ),
    por_empresa as (
        select empresa_id, count(*) as postulados,
               max(applied_at) filter (where orden = cast(:umbral as int) + 1)
                   as cruzo_el_umbral_en
          from sin_revisar
         group by empresa_id
        having count(*) > cast(:umbral as int)
    )
    select pe.empresa_id, e.name as empresa, pe.postulados, pe.cruzo_el_umbral_en,
           r.recordado_en, vi.visto_en,
           coalesce((
               select jsonb_agg(
                          jsonb_build_object('titulo', t.titulo, 'postulados', t.n)
                          order by t.n desc, t.titulo
                      )
                 from (select s.titulo, count(*) as n
                         from sin_revisar s
                        where s.empresa_id = pe.empresa_id
                        group by s.vacante_id, s.titulo) t
           ), '[]'::jsonb) as vacantes,
           array(
               select u.email
                 from public.profiles p
                 join auth.users u on u.id = p.id
                where p.empresa_id = pe.empresa_id
                  and p.role in ('HR', 'Director')
                  and u.email_confirmed_at is not null
                  and u.email is not null
                order by p.created_at
           ) as destinatarios
      from por_empresa pe
      join public.empresas e on e.id = pe.empresa_id
      left join recordado r on r.empresa_id = pe.empresa_id
      left join visto vi on vi.empresa_id = pe.empresa_id
     order by pe.cruzo_el_umbral_en, pe.empresa_id
     limit :limite
    """
)

_ENVIADOS_EN_24_HORAS = text(
    """
    select coalesce(sum(destinatarios), 0) as enviados
      from privado.recordatorios_de_postulados
     where enviado_en > now() - interval '24 hours'
    """
)

_REGISTRAR = text(
    """
    insert into privado.recordatorios_de_postulados (empresa_id, postulados, destinatarios)
    values (:empresa_id, cast(:postulados as int), cast(:destinatarios as int))
    """
)


async def con_postulados_sin_revisar(
    db: AsyncSession, *, umbral: int, limite: int
) -> Sequence[Any]:
    filas = await db.execute(_CON_POSTULADOS_SIN_REVISAR, {"umbral": umbral, "limite": limite})
    return filas.all()


async def enviados_en_24_horas(db: AsyncSession) -> int:
    return int((await db.execute(_ENVIADOS_EN_24_HORAS)).scalar_one())


async def registrar(
    db: AsyncSession, *, empresa_id: UUID, postulados: int, destinatarios: int
) -> None:
    await db.execute(
        _REGISTRAR,
        {"empresa_id": empresa_id, "postulados": postulados, "destinatarios": destinatarios},
    )
