"""SQL de la evaluación con IA del plan de pago (ADR-021, migración 0014).

Corre con la sesión del worker, sin contexto de tenant: el barrido recorre todas
las empresas con IA, lleva su cuenta en `privado` y escribe el resultado en
`applications` y el costo en `runs`.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

AGENT_SKILL = "cv-evaluator"


@dataclass(frozen=True, slots=True)
class ReclamadaRow:
    application_id: UUID
    empresa_id: UUID
    plan: str
    ruta: str
    nombre: str
    correo: str | None
    titulo: str
    descripcion: str
    skills: list[str]
    nivel: str | None
    modalidad: str | None
    ubicacion: str | None
    icp_text: str | None


# El gasto de las dos vías al evaluador, la interna y la del run-token.
_GASTADO_ESTE_MES = text(
    """
    select coalesce(sum(cost_usd), 0)
      from public.runs
     where agent_skill = :agent_skill
       and started_at >= date_trunc('month', now())
    """
)

# Aplicaciones de vacantes abiertas de empresas con IA, en "Aplicados", con CV,
# sin score, sin oposición, no ilegibles, con intentos libres y sin un reclamo
# vigente, de empresas que no llegaron a su tope del mes. `skip locked`: un
# barrido que corre a la vez no toma las mismas. El tope puede pasarse por un
# lote: es de seguridad, no de facturación.
_RECLAMAR = text(
    """
    with candidatas as (
        select a.id as application_id, a.empresa_id
          from public.applications a
          join public.empresas e on e.id = a.empresa_id
          join public.vacantes v on v.id = a.vacante_id
          join public.candidatos c on c.id = a.candidato_id
          left join privado.evaluaciones_ia ev on ev.application_id = a.id
          left join privado.cvs_ilegibles i on i.application_id = a.id
         where e.plan = 'ia'
           and a.status = 'applied'
           and a.fit_score is null
           and not a.sin_ia
           and c.cv_url is not null
           and i.application_id is null
           and v.status in ('open', 'paused')
           and coalesce(ev.intentos, 0) < :max_intentos
           and (ev.reclamada_en is null
                or ev.reclamada_en < now() - make_interval(mins => :minutos_de_reclamo))
           and (select count(*) from privado.evaluaciones_ia x
                 where x.empresa_id = a.empresa_id
                   and x.evaluada_en >= date_trunc('month', now())) < e.ia_cvs_por_mes
         order by a.applied_at, a.id
         limit :limite
           for update of a skip locked
    ),
    reclamadas as (
        insert into privado.evaluaciones_ia as ev (application_id, empresa_id, intentos, reclamada_en)
        select application_id, empresa_id, 1, now() from candidatas
        on conflict (application_id) do update
            set intentos = ev.intentos + 1,
                reclamada_en = now()
        returning ev.application_id
    )
    select a.id as application_id, a.empresa_id, e.plan, c.cv_url as ruta,
           c.full_name as nombre, c.email as correo,
           v.title as titulo, v.jd as descripcion, v.skills,
           v.seniority::text as nivel, v.modality::text as modalidad,
           v.location as ubicacion, v.icp_text
      from reclamadas r
      join public.applications a on a.id = r.application_id
      join public.empresas e on e.id = a.empresa_id
      join public.vacantes v on v.id = a.vacante_id
      join public.candidatos c on c.id = a.candidato_id
     order by a.applied_at, a.id
    """
)

# Solo si el candidato no se opuso y la empresa sigue con IA. El costo se registra
# siempre: el modelo ya cobró.
_GUARDAR = text(
    """
    with guardada as (
        update public.applications a
           set fit_score = :score,
               fit_rationale = :rationale,
               fit_gaps = cast(:gaps as text[]),
               fit_strengths = cast(:strengths as text[]),
               evaluada_en = now(),
               status = case when a.status = 'applied'
                             then 'evaluated'::public.application_status
                             else a.status end
         where a.id = :application_id
           and not a.sin_ia
           and exists (select 1 from public.empresas e
                        where e.id = a.empresa_id and e.plan = 'ia')
        returning a.id
    ),
    cuenta as (
        update privado.evaluaciones_ia
           set evaluada_en = case when exists (select 1 from guardada) then now() end,
               reclamada_en = null,
               ultimo_error = null
         where application_id = :application_id
    ),
    corrida as (
        insert into public.runs (empresa_id, agent_skill, status, cost_usd, cost_cap_usd,
                                 finished_at, payload)
        values (:empresa_id, :agent_skill, 'completed', :costo, :tope, now(),
                jsonb_build_object(
                    'origen', 'interno',
                    'application_id', cast(:application_id as text),
                    'model', cast(:modelo as text),
                    'guardada', exists (select 1 from guardada)))
    )
    select count(*) from guardada
    """
)

_APLAZAR = text(
    """
    with cuenta as (
        update privado.evaluaciones_ia
           set reclamada_en = null,
               ultimo_error = :motivo
         where application_id = :application_id
        returning empresa_id
    )
    insert into public.runs (empresa_id, agent_skill, status, cost_usd, cost_cap_usd,
                             finished_at, error_message, payload)
    select empresa_id, :agent_skill, 'failed', 0, :tope, now(), :motivo,
           jsonb_build_object('origen', 'interno',
                              'application_id', cast(:application_id as text))
      from cuenta
    """
)

_SOLTAR = text(
    """
    update privado.evaluaciones_ia
       set reclamada_en = null,
           intentos = greatest(intentos - 1, 0)
     where application_id = :application_id
    """
)

_MARCAR_ILEGIBLE = text(
    """
    with marcada as (
        insert into privado.cvs_ilegibles (application_id, empresa_id)
        values (:application_id, :empresa_id)
        on conflict (application_id) do nothing
    )
    update privado.evaluaciones_ia
       set reclamada_en = null
     where application_id = :application_id
    """
)


async def gastado_este_mes(db: AsyncSession) -> float:
    return float((await db.execute(_GASTADO_ESTE_MES, {"agent_skill": AGENT_SKILL})).scalar_one())


async def reclamar(
    db: AsyncSession, *, limite: int, max_intentos: int, minutos_de_reclamo: int
) -> list[ReclamadaRow]:
    filas = (
        (
            await db.execute(
                _RECLAMAR,
                {
                    "limite": limite,
                    "max_intentos": max_intentos,
                    "minutos_de_reclamo": minutos_de_reclamo,
                },
            )
        )
        .mappings()
        .all()
    )
    return [
        ReclamadaRow(
            application_id=f["application_id"],
            empresa_id=f["empresa_id"],
            plan=f["plan"],
            ruta=f["ruta"],
            nombre=f["nombre"],
            correo=f["correo"],
            titulo=f["titulo"],
            descripcion=f["descripcion"],
            skills=list(f["skills"]),
            nivel=f["nivel"],
            modalidad=f["modalidad"],
            ubicacion=f["ubicacion"],
            icp_text=f["icp_text"],
        )
        for f in filas
    ]


async def guardar(
    db: AsyncSession,
    *,
    application_id: UUID,
    empresa_id: UUID,
    score: float,
    rationale: str,
    gaps: list[str],
    strengths: list[str],
    costo_usd: float,
    tope_usd: float,
    modelo: str,
) -> bool:
    guardadas = (
        await db.execute(
            _GUARDAR,
            {
                "application_id": str(application_id),
                "empresa_id": str(empresa_id),
                "score": score,
                "rationale": rationale,
                "gaps": gaps,
                "strengths": strengths,
                "costo": costo_usd,
                "tope": tope_usd,
                "modelo": modelo,
                "agent_skill": AGENT_SKILL,
            },
        )
    ).scalar_one()
    return bool(guardadas)


async def aplazar(db: AsyncSession, *, application_id: UUID, motivo: str, tope_usd: float) -> None:
    await db.execute(
        _APLAZAR,
        {
            "application_id": str(application_id),
            "motivo": motivo,
            "tope": tope_usd,
            "agent_skill": AGENT_SKILL,
        },
    )


async def soltar(db: AsyncSession, *, application_id: UUID) -> None:
    await db.execute(_SOLTAR, {"application_id": str(application_id)})


async def marcar_ilegible(db: AsyncSession, *, application_id: UUID, empresa_id: UUID) -> None:
    await db.execute(
        _MARCAR_ILEGIBLE,
        {"application_id": str(application_id), "empresa_id": str(empresa_id)},
    )
