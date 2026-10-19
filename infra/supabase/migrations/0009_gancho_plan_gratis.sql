-- ════════════════════════════════════════════════════════════════════════════
-- Vortex Ops · 0009_gancho_plan_gratis
-- Fecha: 2026-10-19
-- La preselección con IA del plan gratis y su gancho (ADR-017 §3-4, ADR-018).
-- Requiere: 0001..0008
-- ════════════════════════════════════════════════════════════════════════════
--
-- Las aplicaciones de las empresas gratuitas también se evalúan con IA, a ciegas
-- y por instrucción de la empresa. La empresa ve el resumen ("13 de tus 45 CVs
-- califican") y una evaluación de muestra; quién es quién se desbloquea al
-- contratar los servicios de IA. Hasta 0008 eso no se podía garantizar: el
-- score vive en `applications.fit_*`, que la empresa lee con su sesión, así que
-- cualquier evaluación quedaba a la vista por la API.
--
--   · Las preevaluaciones van a `privado.preevaluaciones`. PostgREST no expone
--     el esquema `privado` y `anon`/`authenticated` no tienen permisos en él:
--     solo salen por `resumen_del_gancho()` y `muestra_del_gancho()`.
--   · El resumen avanza por lotes de 5 CVs: si cambiara con cada aplicación,
--     comparar antes y después diría si esa persona califica.
--   · La muestra es una sola evaluación por vacante: la 6.ª por score de las 10
--     primeras (nunca la mejor), fija desde que se elige.
--   · Preseleccionar es una instrucción de la empresa (`vacantes.preseleccion_ia`).
--     Si la apaga, se borra lo evaluado en esa vacante. Si el candidato se opone
--     (`applications.sin_ia`), se borra su evaluación.
--   · Las preevaluaciones de una vacante cerrada se borran a los 30 días
--     (`privado.purgar_preevaluaciones()`, que corre el hr-engine cada día).
--   · Al pasar de `gratis` a `ia`, un trigger copia las preevaluaciones a
--     `applications` y las mueve a "Evaluados": contratar es desbloquear lo que
--     ya existe, sin volver a evaluar.
--   · Una empresa gratuita no puede mover candidatos a las etapas de pago
--     (SQLSTATE `PT403`, que PostgREST responde como 403). Las finales
--     (contratado, descartado, retirado) sí, porque no desbloquean nada.
--
-- La dueña de las reglas es `services/hr-engine/app/domain/gancho.py`, con su
-- contrato en `packages/types/contracts/gancho.json`; los tests de seguridad
-- comprueban que esta copia diga lo mismo.
-- ════════════════════════════════════════════════════════════════════════════

begin;

-- ─── La instrucción de la empresa y la oposición del candidato ──────────────

alter table public.vacantes
    add column if not exists preseleccion_ia boolean not null default true;

comment on column public.vacantes.preseleccion_ia is
    'La empresa pide la preselección a ciegas con IA de esta vacante (ADR-018). Al apagarla se borra lo evaluado.';

alter table public.applications
    add column if not exists sin_ia boolean not null default false;

comment on column public.applications.sin_ia is
    'El candidato se opuso a la evaluación con IA: no se evalúa y se borra la que hubiera.';

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

    -- FK compuesta (0004 §6): del mismo tenant que la aplicación, y se borra con
    -- ella (retención del aviso de privacidad).
    constraint preevaluaciones_application_fk
        foreign key (application_id, empresa_id)
        references public.applications (id, empresa_id) on delete cascade
);

create index if not exists preevaluaciones_empresa_mes_idx
    on privado.preevaluaciones (empresa_id, evaluado_en);

comment on table privado.preevaluaciones is
    'Evaluaciones del plan gratis. Solo salen agregadas o como muestra; se copian a applications al pasar al plan con IA (ADR-018).';

-- CVs de los que no se pudo sacar texto (escaneados o dañados). No se
-- reintentan y no cuentan como "en espera".
create table if not exists privado.cvs_ilegibles (
    application_id uuid primary key,
    empresa_id uuid not null,
    registrado_en timestamptz not null default now(),
    constraint cvs_ilegibles_application_fk
        foreign key (application_id, empresa_id)
        references public.applications (id, empresa_id) on delete cascade
);

-- La evaluación de muestra de cada vacante. La fila se queda aunque esa
-- preevaluación se borre (`set null`): así no se elige otra y la muestra no
-- sirve para ir destapando candidatos de uno en uno.
create table if not exists privado.muestras_del_gancho (
    vacante_id uuid primary key references public.vacantes (id) on delete cascade,
    application_id uuid unique
        references privado.preevaluaciones (application_id) on delete set null,
    elegida_en timestamptz not null default now()
);

-- Última vez que la empresa abrió el pipeline de la vacante. El hr-engine solo
-- preselecciona vacantes vistas en los últimos 14 días: no gasta en cuentas
-- inactivas ni trata CVs que nadie va a mirar. Va aparte de `vacantes` para no
-- tocar su `updated_at` en cada visita.
create table if not exists privado.pipeline_visto (
    vacante_id uuid primary key references public.vacantes (id) on delete cascade,
    visto_en timestamptz not null default now()
);

alter table privado.preevaluaciones enable row level security;
alter table privado.cvs_ilegibles enable row level security;
alter table privado.muestras_del_gancho enable row level security;
alter table privado.pipeline_visto enable row level security;
revoke all on all tables in schema privado from public, anon, authenticated;

-- ─── El gancho ──────────────────────────────────────────────────────────────
--
-- Cero filas si la vacante no es de la empresa de la sesión, si quien pregunta
-- no es HR/Director, si la empresa ya tiene el plan con IA (ahí ve el pipeline
-- completo) o si apagó la preselección.
--
--   califican                = score >= 4, el umbral del psicométrico
--                              (contracts/siguiente-paso.json)
--   cumplen_todas_las_skills = califican y sin gaps frente a la vacante
--   en_espera                = CVs evaluables que todavía no cuentan en el lote
--   ilegibles                = CVs de los que no se pudo sacar texto
create or replace function public.resumen_del_gancho(p_vacante uuid)
    returns table (
        aplicaciones int,
        cvs_evaluados int,
        en_espera int,
        ilegibles int,
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
           and v.preseleccion_ia
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
               count(*) filter (
                   where c.cv_url is not null and not a.sin_ia and i.application_id is null
               )::int as evaluables,
               count(i.application_id)::int as ilegibles
          from public.applications a
          join vacante on vacante.id = a.vacante_id
          join public.candidatos c on c.id = a.candidato_id
          left join privado.cvs_ilegibles i on i.application_id = a.id
    )
    select
        r.aplicaciones,
        (select count(*)::int from lote),
        greatest(0, r.evaluables - (select count(*)::int from lote)),
        r.ilegibles,
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

-- La evaluación de muestra: una sola por vacante, a ciegas (sin aplicación ni
-- nombre). Se elige cuando hay 10 evaluadas: la 6.ª por score de esas 10, con
-- los empates en el orden en que se evaluaron. Desde entonces es siempre la
-- misma. Es `volatile` porque la primera llamada la fija.
create or replace function public.muestra_del_gancho(p_vacante uuid)
    returns table (score numeric, razonamiento text, gaps text[])
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_elegida uuid;
begin
    if not exists (
        select 1
          from public.vacantes v
          join public.empresas e on e.id = v.empresa_id
         where v.id = p_vacante
           and v.empresa_id = public.empresa_id()
           and public.app_role() in ('HR', 'Director', 'SuperAdmin')
           and e.plan = 'gratis'
           and v.preseleccion_ia
    ) then
        return;
    end if;

    if not exists (select 1 from privado.muestras_del_gancho m where m.vacante_id = p_vacante) then
        with primeras as (
            select p.application_id, p.fit_score, p.evaluado_en
              from privado.preevaluaciones p
              join public.applications a on a.id = p.application_id
             where a.vacante_id = p_vacante
             order by p.evaluado_en, p.application_id
             limit 10
        )
        select pr.application_id into v_elegida
          from primeras pr
         where (select count(*) from primeras) = 10
         order by pr.fit_score desc, pr.evaluado_en, pr.application_id
        offset 5
         limit 1;

        if v_elegida is null then
            return;
        end if;
        insert into privado.muestras_del_gancho (vacante_id, application_id)
        values (p_vacante, v_elegida)
        on conflict (vacante_id) do nothing;
    end if;

    return query
        select p.fit_score, p.fit_rationale, p.fit_gaps
          from privado.muestras_del_gancho m
          join privado.preevaluaciones p on p.application_id = m.application_id
         where m.vacante_id = p_vacante;
end;
$$;

revoke execute on function public.muestra_del_gancho(uuid) from public, anon;
grant execute on function public.muestra_del_gancho(uuid) to authenticated;

-- El panel la llama al abrir el pipeline de una vacante.
create or replace function public.registrar_visita_al_pipeline(p_vacante uuid)
    returns void
    language sql
    volatile
    security definer
    set search_path = ''
as $$
    insert into privado.pipeline_visto (vacante_id, visto_en)
    select v.id, now()
      from public.vacantes v
     where v.id = p_vacante
       and v.empresa_id = public.empresa_id()
       and public.app_role() in ('HR', 'Director', 'SuperAdmin')
    on conflict (vacante_id) do update set visto_en = excluded.visto_en;
$$;

revoke execute on function public.registrar_visita_al_pipeline(uuid) from public, anon;
grant execute on function public.registrar_visita_al_pipeline(uuid) to authenticated;

-- ─── Borrado: instrucción retirada, oposición y vacante cerrada ─────────────

create or replace function public.vacantes_sin_preseleccion_borra_lo_evaluado()
    returns trigger
    language plpgsql
    security definer
    set search_path = ''
as $$
begin
    delete from privado.preevaluaciones p
     using public.applications a
     where p.application_id = a.id
       and a.vacante_id = new.id;
    delete from privado.cvs_ilegibles i
     using public.applications a
     where i.application_id = a.id
       and a.vacante_id = new.id;
    return null;
end;
$$;

drop trigger if exists vacantes_preseleccion_apagada on public.vacantes;
create trigger vacantes_preseleccion_apagada
    after update of preseleccion_ia on public.vacantes
    for each row
    when (old.preseleccion_ia and not new.preseleccion_ia)
    execute function public.vacantes_sin_preseleccion_borra_lo_evaluado();

-- La oposición alcanza también al plan con IA: se borra el score de
-- `applications`, no solo la preevaluación.
create or replace function public.applications_oposicion_a_la_ia()
    returns trigger
    language plpgsql
    security definer
    set search_path = ''
as $$
begin
    delete from privado.preevaluaciones where application_id = new.id;
    new.fit_score := null;
    new.fit_rationale := null;
    new.fit_gaps := '{}';
    return new;
end;
$$;

drop trigger if exists applications_oposicion_a_la_ia on public.applications;
create trigger applications_oposicion_a_la_ia
    before update of sin_ia on public.applications
    for each row
    when (not old.sin_ia and new.sin_ia)
    execute function public.applications_oposicion_a_la_ia();

-- La corre el hr-engine una vez al día con el rol dueño. Devuelve cuántas borró.
create or replace function privado.purgar_preevaluaciones(p_dias int default 30)
    returns int
    language plpgsql
    security definer
    set search_path = ''
as $$
declare
    v_borradas int;
begin
    delete from privado.preevaluaciones p
     using public.applications a, public.vacantes v
     where p.application_id = a.id
       and v.id = a.vacante_id
       and v.status = 'closed'
       and v.closed_at < now() - make_interval(days => p_dias);
    get diagnostics v_borradas = row_count;
    return v_borradas;
end;
$$;

revoke all on function privado.purgar_preevaluaciones(int) from public, anon, authenticated;

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

drop trigger if exists empresas_desbloqueo_al_contratar on public.empresas;
create trigger empresas_desbloqueo_al_contratar
    after update of plan on public.empresas
    for each row
    when (old.plan = 'gratis' and new.plan = 'ia')
    execute function public.empresas_desbloquea_preevaluaciones();

-- Las funciones de trigger no se llaman a mano.
revoke execute on function public.vacantes_sin_preseleccion_borra_lo_evaluado() from public, anon, authenticated;
revoke execute on function public.applications_oposicion_a_la_ia() from public, anon, authenticated;
revoke execute on function public.applications_respeta_etapas_del_plan() from public, anon, authenticated;
revoke execute on function public.empresas_desbloquea_preevaluaciones() from public, anon, authenticated;

commit;
