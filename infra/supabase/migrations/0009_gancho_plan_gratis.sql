-- ════════════════════════════════════════════════════════════════════════════
-- Vortex Ops · 0009_gancho_plan_gratis
-- Fecha: 2026-10-19
-- El gancho del pipeline gratis y las etapas del plan (ADR-017 §3-4, ADR-018).
-- Requiere: 0001..0008
-- ════════════════════════════════════════════════════════════════════════════
--
-- Las aplicaciones de las empresas gratuitas también se evalúan con IA, pero la
-- empresa solo ve el resumen ("13 de tus 45 CVs califican"). Quién es quién se
-- desbloquea al contratar los servicios de IA. Hasta 0008 eso no se podía
-- garantizar: el score vive en `applications.fit_*`, y la empresa lee esa tabla
-- con su sesión, así que cualquier evaluación quedaba a la vista por la API.
--
--   · Las preevaluaciones del plan gratis van a `privado.preevaluaciones`. El
--     esquema `privado` no lo expone PostgREST y `anon`/`authenticated` no
--     tienen ningún permiso sobre él: la única salida es `resumen_del_gancho()`.
--   · `resumen_del_gancho()` devuelve conteos por lotes de 5 CVs. Si los números
--     cambiaran con cada aplicación, comparar antes y después diría si esa
--     persona califica. Con lotes, lo mínimo que se puede deducir es de 5.
--   · Al pasar de `gratis` a `ia`, un trigger copia las preevaluaciones a
--     `applications` y las mueve a "Evaluados": contratar es desbloquear lo que
--     ya existe, sin volver a evaluar ni pagar dos veces el modelo.
--   · Una empresa gratuita no puede mover candidatos a las etapas de pago
--     (SQLSTATE `PT403`, que PostgREST responde como 403). Las finales
--     (contratado, descartado, retirado) sí, porque no desbloquean nada.
--
-- La dueña de la regla del gancho es `services/hr-engine/app/domain/gancho.py`,
-- con su contrato en `packages/types/contracts/gancho.json`; los tests de
-- seguridad comprueban que esta copia diga lo mismo.
-- ════════════════════════════════════════════════════════════════════════════

begin;

-- ─── Esquema privado ────────────────────────────────────────────────────────
--
-- Fuera de `public` a propósito: Supabase da permisos por defecto a `anon` y
-- `authenticated` sobre cada tabla nueva de `public`, y un `grant ... on all
-- tables in schema public` de un tutorial bastaría para exponerla.

create schema if not exists privado;
revoke all on schema privado from public, anon, authenticated;

create table if not exists privado.preevaluaciones (
    application_id uuid primary key,
    empresa_id uuid not null,
    fit_score numeric(3, 1) not null check (fit_score >= 0 and fit_score <= 10),
    fit_rationale text not null,
    fit_gaps text[] not null default '{}',
    -- Lo que tardó el modelo con este CV: la suma es el "en 38 segundos".
    duracion_ms integer not null check (duracion_ms >= 0),
    modelo text not null,
    costo_usd numeric(10, 6) not null default 0 check (costo_usd >= 0),
    evaluado_en timestamptz not null default now(),

    -- FK compuesta (0004 §6): la preevaluación es del mismo tenant que la
    -- aplicación, y se borra con ella (retención del aviso de privacidad).
    constraint preevaluaciones_application_fk
        foreign key (application_id, empresa_id)
        references public.applications (id, empresa_id) on delete cascade
);

create index if not exists preevaluaciones_empresa_mes_idx
    on privado.preevaluaciones (empresa_id, evaluado_en);

alter table privado.preevaluaciones enable row level security;
revoke all on privado.preevaluaciones from public, anon, authenticated;

comment on table privado.preevaluaciones is
    'Evaluaciones del plan gratis. Solo las lee resumen_del_gancho(); se copian a applications al pasar al plan con IA (ADR-018).';

-- ─── El gancho ──────────────────────────────────────────────────────────────
--
-- Cero filas si la vacante no es de la empresa de la sesión, si quien pregunta
-- no es HR/Director o si la empresa ya tiene el plan con IA (ahí ve el pipeline
-- completo y el gancho sobra).
--
--   califican                = score >= 4, el umbral del psicométrico
--                              (contracts/siguiente-paso.json)
--   cumplen_todas_las_skills = califican y sin gaps frente a la vacante
--   en_espera                = CVs recibidos que todavía no cuentan en el lote
create or replace function public.resumen_del_gancho(p_vacante uuid)
    returns table (
        aplicaciones int,
        cvs_evaluados int,
        en_espera int,
        segundos int,
        califican int,
        cumplen_todas_las_skills int
    )
    language sql
    stable
    security definer
    set search_path = ''
as $$
    with vacante as (
        select v.id
          from public.vacantes v
          join public.empresas e on e.id = v.empresa_id
         where v.id = p_vacante
           and v.empresa_id = public.empresa_id()
           and public.app_role() in ('HR', 'Director', 'SuperAdmin')
           and e.plan = 'gratis'
    ),
    evaluadas as (
        select p.fit_score, p.fit_gaps, p.duracion_ms,
               row_number() over (order by p.evaluado_en, p.application_id) as orden,
               count(*) over () as total
          from privado.preevaluaciones p
          join public.applications a on a.id = p.application_id
          join vacante on vacante.id = a.vacante_id
    ),
    lote as (
        select * from evaluadas where orden <= (total / 5) * 5
    ),
    recibidas as (
        select count(*)::int as aplicaciones,
               count(*) filter (where c.cv_url is not null)::int as con_cv
          from public.applications a
          join vacante on vacante.id = a.vacante_id
          join public.candidatos c on c.id = a.candidato_id
    )
    select
        r.aplicaciones,
        (select count(*)::int from lote),
        greatest(0, r.con_cv - (select count(*)::int from lote)),
        -- pg_catalog explícito: pgvector define otro `sum` en public.
        coalesce(ceil((select pg_catalog.sum(l.duracion_ms) from lote l) / 1000.0), 0)::int,
        (select count(*)::int from lote l where l.fit_score >= 4.0),
        (select count(*)::int from lote l
          where l.fit_score >= 4.0 and cardinality(l.fit_gaps) = 0)
      from recibidas r
     where exists (select 1 from vacante);
$$;

revoke execute on function public.resumen_del_gancho(uuid) from public, anon;
grant execute on function public.resumen_del_gancho(uuid) to authenticated;

-- ─── Etapas del pipeline por plan ───────────────────────────────────────────
--
-- Las etapas que el plan gratis no ve son las de `contracts/limites-plan.json`
-- (`etapas_visibles` del plan con IA menos las del gratis).
create or replace function public.applications_respeta_etapas_del_plan()
    returns trigger
    language plpgsql
    security definer
    set search_path = ''
as $$
begin
    if tg_op = 'UPDATE' and new.status = old.status then
        return new;
    end if;
    if new.status in ('evaluated', 'shortlisted', 'interviewed', 'offered')
       and (select e.plan from public.empresas e where e.id = new.empresa_id) = 'gratis' then
        raise exception 'etapa del pipeline no incluida en el plan gratis'
            using errcode = 'PT403',
                  hint = 'Las etapas después de Aplicados son parte de los servicios de IA.';
    end if;
    return new;
end;
$$;

drop trigger if exists applications_etapas_del_plan on public.applications;
create trigger applications_etapas_del_plan
    before insert or update of status on public.applications
    for each row execute function public.applications_respeta_etapas_del_plan();

-- ─── Desbloqueo al contratar ────────────────────────────────────────────────
--
-- `after update`: cuando corre, la empresa ya es `ia` y el trigger de etapas
-- deja pasar "Evaluados". La copia privada se borra: el dato vive ya en
-- `applications` y no hace falta tenerlo dos veces.
create or replace function public.empresas_desbloquea_preevaluaciones()
    returns trigger
    language plpgsql
    security definer
    set search_path = ''
as $$
begin
    update public.applications a
       set fit_score = p.fit_score,
           fit_rationale = p.fit_rationale,
           fit_gaps = p.fit_gaps,
           status = case when a.status = 'applied'
                         then 'evaluated'::public.application_status
                         else a.status end
      from privado.preevaluaciones p
     where p.application_id = a.id
       and p.empresa_id = new.id;

    delete from privado.preevaluaciones where empresa_id = new.id;
    return null;
end;
$$;

revoke execute on function public.empresas_desbloquea_preevaluaciones() from public, anon, authenticated;

drop trigger if exists empresas_desbloqueo_al_contratar on public.empresas;
create trigger empresas_desbloqueo_al_contratar
    after update of plan on public.empresas
    for each row
    when (old.plan = 'gratis' and new.plan = 'ia')
    execute function public.empresas_desbloquea_preevaluaciones();

commit;
