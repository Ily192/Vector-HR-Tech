"""SQL de la coincidencia de skills del plan gratis (ADR-019, migración 0010).

Corre con la sesión del worker, sin contexto de tenant: el barrido recorre todas
las empresas gratuitas y escribe en `privado`, que ningún rol de la API toca.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class PendienteRow:
    application_id: UUID
    empresa_id: UUID
    ruta: str
    skills: list[str]


# Aplicaciones de vacantes abiertas de empresas gratuitas, con CV y skills, sin
# oposición del candidato, no ilegibles y sin coincidencia con las skills de hoy.
# Las de vacantes cerradas no: la purga las borraría y el barrido las volvería a
# calcular sin fin.
_PENDIENTES = text(
    """
    select a.id as application_id, a.empresa_id, c.cv_url as ruta, v.skills
      from public.applications a
      join public.vacantes v on v.id = a.vacante_id
      join public.empresas e on e.id = a.empresa_id
      join public.candidatos c on c.id = a.candidato_id
      left join privado.coincidencias co
             on co.application_id = a.id and co.skills = v.skills
      left join privado.cvs_ilegibles i on i.application_id = a.id
     where e.plan = 'gratis'
       and v.status in ('open', 'paused')
       and cardinality(v.skills) > 0
       and c.cv_url is not null
       and not a.sin_ia
       and co.application_id is null
       and i.application_id is null
     order by a.applied_at, a.id
     limit :limite
    """
)

# Solo si la vacante sigue pidiendo esas skills y el candidato no se opuso.
# Guardarla quita la marca de ilegible que el caso de uso pone antes de leer.
_GUARDAR = text(
    """
    with guardada as (
        insert into privado.coincidencias (application_id, empresa_id, skills, encontradas)
        select a.id, a.empresa_id, cast(:skills as text[]), cast(:encontradas as text[])
          from public.applications a
          join public.vacantes v on v.id = a.vacante_id
         where a.id = :application_id
           and v.skills = cast(:skills as text[])
           and not a.sin_ia
        on conflict (application_id) do update
            set skills = excluded.skills,
                encontradas = excluded.encontradas,
                calculado_en = now()
        returning application_id
    ),
    desmarcada as (
        delete from privado.cvs_ilegibles i
         using guardada g
         where i.application_id = g.application_id
    )
    select count(*) from guardada
    """
)

_MARCAR_ILEGIBLE = text(
    """
    insert into privado.cvs_ilegibles (application_id, empresa_id)
    values (:application_id, :empresa_id)
    on conflict (application_id) do nothing
    """
)

_DESMARCAR_ILEGIBLE = text(
    "delete from privado.cvs_ilegibles where application_id = :application_id"
)

_PURGAR = text("select privado.purgar_coincidencias(:dias)")


async def pendientes(db: AsyncSession, limite: int) -> list[PendienteRow]:
    filas = (await db.execute(_PENDIENTES, {"limite": limite})).mappings().all()
    return [
        PendienteRow(
            application_id=f["application_id"],
            empresa_id=f["empresa_id"],
            ruta=f["ruta"],
            skills=list(f["skills"]),
        )
        for f in filas
    ]


async def guardar(
    db: AsyncSession,
    *,
    application_id: UUID,
    skills: list[str],
    encontradas: list[str],
) -> bool:
    guardadas = (
        await db.execute(
            _GUARDAR,
            {
                "application_id": str(application_id),
                "skills": skills,
                "encontradas": encontradas,
            },
        )
    ).scalar_one()
    return bool(guardadas)


async def marcar_ilegible(db: AsyncSession, *, application_id: UUID, empresa_id: UUID) -> None:
    await db.execute(
        _MARCAR_ILEGIBLE,
        {"application_id": str(application_id), "empresa_id": str(empresa_id)},
    )


async def desmarcar_ilegible(db: AsyncSession, *, application_id: UUID) -> None:
    await db.execute(_DESMARCAR_ILEGIBLE, {"application_id": str(application_id)})


async def purgar(db: AsyncSession, *, dias: int) -> int:
    """Borra las coincidencias de vacantes cerradas hace más de `dias`. Devuelve cuántas."""
    return int((await db.execute(_PURGAR, {"dias": dias})).scalar_one())
