"""SQL de la moderación de vacantes (ADR-022, migración 0019).

Corre con la sesión del hr-engine con el rol dueño y sin contexto de tenant, como
el barrido de coincidencias. Por eso puede escribir `vacantes.moderacion`: el
trigger de 0019 solo la protege de las sesiones de tenant (el panel).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

#: Con menos caracteres, dos descripciones iguales no dicen nada ("Ventas.").
MIN_LARGO_PARA_DUPLICADO = 120

# Abiertas en 'pendiente', con el contexto de su empresa. `skip locked`: si un
# barrido se encima con otro, no moderan la misma vacante dos veces.
_PENDIENTES = text(
    """
    select v.id, v.empresa_id, v.title as titulo, v.jd as descripcion,
           e.verificada, e.publica_para,
           e.created_at > now() - make_interval(days => cast(:dias as int)) as cuenta_nueva,
           exists (
               select 1 from public.vacantes o
                where o.empresa_id = v.empresa_id
                  and o.id <> v.id
                  and o.moderacion = 'publicada'
           ) as tiene_publicadas,
           (select count(*) from public.vacantes o
             where o.empresa_id = v.empresa_id
               and o.created_at > now() - interval '1 hour') as creadas_en_la_ultima_hora,
           (char_length(v.jd) >= cast(:min_dup as int) and exists (
               select 1 from public.vacantes o
                where o.empresa_id <> v.empresa_id
                  and lower(regexp_replace(o.jd, '\\s+', ' ', 'g'))
                      = lower(regexp_replace(v.jd, '\\s+', ' ', 'g'))
           )) as duplicada
      from public.vacantes v
      join public.empresas e on e.id = v.empresa_id
     where v.moderacion = 'pendiente'
       and v.status = 'open'
     order by v.created_at, v.id
     limit :lote
       for update of v skip locked
    """
)

# Solo si sigue 'pendiente' y abierta: si la editaron entre leerla y guardarla,
# vuelve a 'pendiente' sola y la toma el siguiente barrido.
_GUARDAR = text(
    """
    update public.vacantes
       set moderacion = cast(:estado as public.moderacion_vacante),
           motivos_moderacion = cast(:motivos as jsonb),
           moderada_en = now(),
           revision_avisada_en = null
     where id = :id
       and moderacion = 'pendiente'
       and status = 'open'
    returning id
    """
)

_EN_COLA = """
    select v.id, v.title as titulo, v.jd as descripcion, e.name as empresa,
           e.verificada, e.publica_para, v.moderacion, v.motivos_moderacion
      from public.vacantes v
      join public.empresas e on e.id = v.empresa_id
"""

_COLA_SIN_AVISAR = text(
    _EN_COLA
    + """
     where v.moderacion in ('en_revision', 'oculta')
       and v.status = 'open'
       and v.revision_avisada_en is null
     order by (v.moderacion = 'oculta') desc, v.moderada_en nulls last, v.created_at
     limit :limite
    """
)

_UNA = text(_EN_COLA + " where v.id = :id")

_COLA_COMPLETA = text(
    _EN_COLA
    + """
     where v.moderacion in ('en_revision', 'oculta')
       and v.status = 'open'
     order by (v.moderacion = 'oculta') desc, v.moderada_en nulls last, v.created_at
    """
)

_MARCAR_AVISADAS = text(
    """
    update public.vacantes
       set revision_avisada_en = now()
     where id = any(cast(:ids as uuid[]))
    """
)

_AVISOS_RECIENTES = text(
    """
    select max(enviado_en) as ultimo,
           count(*) filter (where enviado_en > now() - interval '24 hours') as ultimas
      from privado.avisos_de_moderacion
    """
)

_REGISTRAR_AVISO = text(
    """
    insert into privado.avisos_de_moderacion (urgente, vacantes)
    values (cast(:urgente as boolean), cast(:vacantes as int))
    """
)

_RESOLVER = text(
    """
    update public.vacantes
       set moderacion = cast(:estado as public.moderacion_vacante),
           motivos_moderacion = case
               when cast(:motivo as jsonb) is null then motivos_moderacion
               else motivos_moderacion || jsonb_build_array(cast(:motivo as jsonb))
           end,
           moderada_en = now(),
           revision_avisada_en = coalesce(revision_avisada_en, now())
     where id = :id
       and moderacion = any(cast(:desde as public.moderacion_vacante[]))
    returning id
    """
)

# Suma la insignia, nunca la quita sola; un reclutador nunca la lleva. En el SET,
# `verificada` y `verificada_en` son los valores de antes del update.
_GUARDAR_VERIFICACION = text(
    """
    update public.empresas
       set publica_para = cast(:publica_para as text),
           web = cast(:web as text),
           linkedin = cast(:linkedin as text),
           verificada = case
               when cast(:publica_para as text) = 'clientes' then false
               else verificada or cast(:verificada as boolean)
           end,
           verificada_en = case
               when cast(:publica_para as text) = 'clientes' then null
               when verificada then verificada_en
               when cast(:verificada as boolean) then now()
           end
     where id = :id
    returning verificada
    """
)

_EMPRESA_POR_CORREO = text(
    """
    select p.empresa_id
      from public.profiles p
     where lower(p.email) = lower(:correo)
     order by p.created_at
     limit 1
    """
)


async def pendientes(db: AsyncSession, *, lote: int, dias: int) -> Sequence[Any]:
    filas = await db.execute(
        _PENDIENTES, {"lote": lote, "dias": dias, "min_dup": MIN_LARGO_PARA_DUPLICADO}
    )
    return filas.all()


async def guardar(db: AsyncSession, *, vacante_id: UUID, estado: str, motivos: str) -> bool:
    fila = await db.execute(_GUARDAR, {"id": vacante_id, "estado": estado, "motivos": motivos})
    return fila.first() is not None


async def cola_sin_avisar(db: AsyncSession, limite: int) -> Sequence[Any]:
    return (await db.execute(_COLA_SIN_AVISAR, {"limite": limite})).all()


async def cola_completa(db: AsyncSession) -> Sequence[Any]:
    return (await db.execute(_COLA_COMPLETA)).all()


async def una(db: AsyncSession, vacante_id: UUID) -> Any | None:
    return (await db.execute(_UNA, {"id": vacante_id})).first()


async def marcar_avisadas(db: AsyncSession, ids: Sequence[UUID]) -> None:
    await db.execute(_MARCAR_AVISADAS, {"ids": [str(i) for i in ids]})


async def avisos_recientes(db: AsyncSession) -> Any:
    return (await db.execute(_AVISOS_RECIENTES)).one()


async def registrar_aviso(db: AsyncSession, *, urgente: bool, vacantes: int) -> None:
    await db.execute(_REGISTRAR_AVISO, {"urgente": urgente, "vacantes": vacantes})


async def resolver(
    db: AsyncSession,
    *,
    vacante_id: UUID,
    estado: str,
    motivo: str | None,
    desde: Sequence[str],
) -> bool:
    fila = await db.execute(
        _RESOLVER,
        {"id": vacante_id, "estado": estado, "motivo": motivo, "desde": list(desde)},
    )
    return fila.first() is not None


async def guardar_verificacion(
    db: AsyncSession,
    *,
    empresa_id: UUID,
    publica_para: str,
    web: str | None,
    linkedin: str | None,
    verificada: bool,
) -> bool | None:
    """Si la empresa quedó verificada; `None` si no existe."""
    fila = (
        await db.execute(
            _GUARDAR_VERIFICACION,
            {
                "id": empresa_id,
                "publica_para": publica_para,
                "web": web,
                "linkedin": linkedin,
                "verificada": verificada,
            },
        )
    ).first()
    return None if fila is None else bool(fila.verificada)


async def empresa_por_correo(db: AsyncSession, correo: str) -> UUID | None:
    fila = (await db.execute(_EMPRESA_POR_CORREO, {"correo": correo})).first()
    return fila.empresa_id if fila else None
