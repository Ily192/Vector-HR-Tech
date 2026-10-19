-- ════════════════════════════════════════════════════════════════════════════
-- Vortex Ops · 0010_plan_gratis_sin_ia
-- Fecha: 2026-10-19
-- El plan gratis no usa IA, y lo gratis queda separado de lo de pago (ADR-019).
-- Requiere: 0001..0009
-- ════════════════════════════════════════════════════════════════════════════
--
-- Ilyra descartó la preselección con IA del plan gratis (ADR-018). La empresa
-- gratuita recibe sus aplicaciones y las descarga en un .zip; la IA es lo que se
-- paga. Esta migración quita lo que 0009 había montado para evaluar con IA y
-- cierra los huecos por los que el plan gratis llegaba a lo de pago:
--
--   · El gancho es una coincidencia de skills sin IA: cuántos CVs mencionan
--     las skills que pide la vacante (`vacantes.skills`). La calcula el
--     hr-engine con texto plano y la guarda en `privado.coincidencias`. La
--     empresa solo ve el resumen por lotes de 5 (`resumen_del_gancho()`),
--     nunca quién es quién.
--   · Se van las preevaluaciones, la muestra, las visitas al pipeline, el
--     interruptor `vacantes.preseleccion_ia` y el desbloqueo al contratar.
--   · El tope de 50 aplicaciones cuenta las recibidas, entren por el career site
--     o por la API, y borrar o descartar no libera cupo. Hasta ahora solo lo
--     aplicaba `aplicar_a_vacante()`: la empresa podía insertar aplicaciones con
--     su sesión sin tope, o borrar 50 para recibir otras 50.
--   · Entrevistas, psicométricos y constancias son del cockpit. Nada impedía
--     a una empresa gratuita crearlos por la API. Ahora devuelve PT403.
--   · La oposición del candidato (`applications.sin_ia`) no la retira la
--     empresa, y el career site ya puede recibirla (`aplicar_a_vacante`).
--   · En 30 días se publican tantas vacantes nuevas como activas permite el
--     plan: cerrar una y publicar otra ya no da un plan gratis sin fin.
--     `mi_cupo_de_vacantes()` lo informa y deja de decir "0 libres" al plan con IA.
--
-- Las reglas del gancho tienen su dueña en `services/hr-engine/app/domain/`
-- (`gancho.py` para el resumen, `coincidencia.py` para comparar el CV), con su
-- contrato en `packages/types/contracts/gancho.json`. Los límites del plan
-- siguen en `domain/plan.py` y `contracts/limites-plan.json`.
-- ════════════════════════════════════════════════════════════════════════════

begin;

-- ─── 1. Fuera la IA del plan gratis (0009) ──────────────────────────────────

drop trigger if exists empresas_desbloqueo_al_contratar on public.empresas;
drop function if exists public.empresas_desbloquea_preevaluaciones();
drop trigger if exists vacantes_preseleccion_apagada on public.vacantes;
drop function if exists public.vacantes_sin_preseleccion_borra_lo_evaluado();
drop function if exists public.muestra_del_gancho(uuid);
drop function if exists public.registrar_visita_al_pipeline(uuid);
drop function if exists public.resumen_del_gancho(uuid);
drop function if exists privado.purgar_preevaluaciones(int);
drop table if exists privado.muestras_del_gancho;
drop table if exists privado.pipeline_visto;
drop table if exists privado.preevaluaciones;

alter table public.vacantes drop column if exists preseleccion_ia;

comment on column public.applications.sin_ia is
    'El candidato se opuso a la evaluación automatizada: no entra en la coincidencia de skills ni en la evaluación con IA, y se borra la que hubiera. Solo él la retira (ADR-019).';

-- ─── 2. Las skills de la vacante ────────────────────────────────────────────
--
-- Las escribe la empresa en "Crear empleo", como las pondría un candidato en su
-- CV. Sin skills no hay coincidencia que calcular: el panel le pide agregarlas.
create or replace function public.skills_validas(p_skills text[])
    returns boolean
    language sql
    immutable
    set search_path = ''
as $$
    select p_skills is not null
       and cardinality(p_skills) <= 15
       and not exists (
           select 1
             from unnest(p_skills) s
            where s is null or length(btrim(s)) not between 1 and 60
       );
$$;

alter table public.vacantes
    add column if not exists skills text[] not null default '{}';

alter table public.vacantes drop constraint if exists vacantes_skills_validas;
alter table public.vacantes
    add constraint vacantes_skills_validas check (public.skills_validas(skills));

comment on column public.vacantes.skills is
    'Skills que pide la vacante (hasta 15). El plan gratis cuenta cuántos CVs las mencionan, sin IA (ADR-019).';

-- ─── 3. La coincidencia de skills ───────────────────────────────────────────
--
-- Una fila por aplicación: qué skills de la vacante menciona su CV. Va en
-- `privado` por lo mismo que las preevaluaciones de 0009: si la empresa la
-- leyera, el gancho dejaría de ser un gancho.
create table if not exists privado.coincidencias (
    application_id uuid primary key,
    empresa_id uuid not null,
    -- Las skills de la vacante con las que se calculó. Si la empresa las cambia,
    -- la fila deja de contar hasta que el hr-engine la recalcule.
    skills text[] not null check (cardinality(skills) between 1 and 15),
    -- Las que el CV menciona, en el orden de `skills`.
    encontradas text[] not null default '{}',
    calculado_en timestamptz not null default now(),

    constraint coincidencias_de_la_vacante check (encontradas <@ skills),
    constraint coincidencias_application_fk
        foreign key (application_id, empresa_id)
        references public.applications (id, empresa_id) on delete cascade
);

create index if not exists coincidencias_empresa_idx on privado.coincidencias (empresa_id);

comment on table privado.coincidencias is
    'Qué skills de la vacante menciona cada CV del plan gratis. Sin IA. Solo sale agregada por resumen_del_gancho() (ADR-019).';

alter table privado.coincidencias enable row level security;
revoke all on privado.coincidencias from public, anon, authenticated;

-- ─── 4. El gancho ───────────────────────────────────────────────────────────
--
-- Cero filas si la vacante no es de la empresa de la sesión, si quien pregunta
-- no es HR/Director o si la empresa tiene el plan con IA (ahí la evaluación con
-- IA reemplaza al gancho).
--
--   skills          = skills que pide la vacante; con 0 no hay nada que contar
--   revisados       = CVs que ya cuentan: solo lotes completos de 5
--   en_espera       = CVs revisables que todavía no entran en un lote
--   ilegibles       = CVs de los que no se pudo sacar texto
--   con_la_mayoria  = mencionan más de la mitad de las skills (incluye con_todas)
--   con_todas       = mencionan todas
create function public.resumen_del_gancho(p_vacante uuid)
    returns table (
        aplicaciones int,
        skills int,
        revisados int,
        en_espera int,
        ilegibles int,
        con_la_mayoria int,
        con_todas int
    )
    language sql
    stable
    security definer
    set search_path = ''
as $$
    with vacante as (
        select v.id, v.skills, cardinality(v.skills) as total
          from public.vacantes v
          join public.empresas e on e.id = v.empresa_id
         where v.id = p_vacante
           and v.empresa_id = public.empresa_id()
           and public.app_role() in ('HR', 'Director', 'SuperAdmin')
           and e.plan = 'gratis'
    ),
    vigentes as (
        select cardinality(c.encontradas) as encontradas,
               row_number() over (order by c.calculado_en, c.application_id) as orden,
               count(*) over () as total
          from privado.coincidencias c
          join public.applications a on a.id = c.application_id
          join vacante on vacante.id = a.vacante_id
         where c.skills = vacante.skills
           and not a.sin_ia
    ),
    lote as (
        select l.encontradas from vigentes l where l.orden <= (l.total / 5) * 5
    ),
    recibidas as (
        select count(*)::int as aplicaciones,
               count(*) filter (
                   where c.cv_url is not null and not a.sin_ia and i.application_id is null
               )::int as revisables,
               count(i.application_id)::int as ilegibles
          from public.applications a
          join vacante on vacante.id = a.vacante_id
          join public.candidatos c on c.id = a.candidato_id
          left join privado.cvs_ilegibles i on i.application_id = a.id
    )
    select r.aplicaciones,
           v.total,
           (select count(*)::int from lote),
           case when v.total = 0 then 0
                else greatest(0, r.revisables - (select count(*)::int from lote)) end,
           r.ilegibles,
           (select count(*)::int from lote l where l.encontradas * 2 > v.total),
           (select count(*)::int from lote l where l.encontradas = v.total)
      from recibidas r
      cross join vacante v;
$$;

revoke execute on function public.resumen_del_gancho(uuid) from public, anon;
grant execute on function public.resumen_del_gancho(uuid) to authenticated;

-- ─── 5. Cuándo se borra ─────────────────────────────────────────────────────

-- La oposición del candidato alcanza a los dos planes: se borra su coincidencia
-- y el score del plan con IA.
create or replace function public.applications_oposicion_a_la_ia()
    returns trigger
    language plpgsql
    security definer
    set search_path = ''
as $$
begin
    delete from privado.coincidencias where application_id = new.id;
    new.fit_score := null;
    new.fit_rationale := null;
    new.fit_gaps := '{}';
    return new;
end;
$$;

-- La empresa no puede retirar la oposición de un candidato: solo él, a través
-- de Vector HR (sin sesión de tenant: rol dueño o clave secreta).
create or replace function public.applications_oposicion_irrevocable()
    returns trigger
    language plpgsql
    set search_path = ''
as $$
begin
    if public.empresa_id() is not null then
        raise exception 'la oposición del candidato no la puede retirar la empresa'
            using errcode = 'PT403',
                  hint = 'Solo el candidato puede retirarla, a través de Vector HR.';
    end if;
    return new;
end;
$$;

drop trigger if exists applications_oposicion_irrevocable on public.applications;
create trigger applications_oposicion_irrevocable
    before update of sin_ia on public.applications
    for each row
    when (old.sin_ia and not new.sin_ia)
    execute function public.applications_oposicion_irrevocable();

-- Al contratar, el gancho ya cumplió: la evaluación con IA lo reemplaza.
create or replace function public.empresas_al_contratar_borra_el_gancho()
    returns trigger
    language plpgsql
    security definer
    set search_path = ''
as $$
begin
    delete from privado.coincidencias where empresa_id = new.id;
    delete from privado.cvs_ilegibles where empresa_id = new.id;
    return null;
end;
$$;

drop trigger if exists empresas_al_contratar on public.empresas;
create trigger empresas_al_contratar
    after update of plan on public.empresas
    for each row
    when (old.plan = 'gratis' and new.plan = 'ia')
    execute function public.empresas_al_contratar_borra_el_gancho();

-- La corre el hr-engine una vez al día con el rol dueño. Devuelve cuántas
-- coincidencias borró; los CVs ilegibles de esas vacantes se van con ellas.
create or replace function privado.purgar_coincidencias(p_dias int default 30)
    returns int
    language plpgsql
    security definer
    set search_path = ''
as $$
declare
    v_borradas int;
begin
    delete from privado.coincidencias c
     using public.applications a, public.vacantes v
     where c.application_id = a.id
       and v.id = a.vacante_id
       and v.status = 'closed'
       and v.closed_at < now() - make_interval(days => p_dias);
    get diagnostics v_borradas = row_count;

    delete from privado.cvs_ilegibles i
     using public.applications a, public.vacantes v
     where i.application_id = a.id
       and v.id = a.vacante_id
       and v.status = 'closed'
       and v.closed_at < now() - make_interval(days => p_dias);
    return v_borradas;
end;
$$;

revoke all on function privado.purgar_coincidencias(int) from public, anon, authenticated;

-- ─── 6. Tope de aplicaciones: cuenta las recibidas ──────────────────────────
--
-- Un contador por vacante que solo sube. Va en `privado` porque la empresa
-- actualiza sus vacantes con su sesión y podría ponerlo en cero. El upsert
-- bloquea la fila de la vacante, así que dos aplicaciones simultáneas no pasan
-- las dos con el último cupo. Es el contador que ADR-017 preveía y que 0008
-- cambió por un `count(*)`: contar las filas que quedan dejaba que borrar
-- liberara cupo.
create table if not exists privado.aplicaciones_recibidas (
    vacante_id uuid primary key references public.vacantes (id) on delete cascade,
    recibidas int not null default 0 check (recibidas >= 0)
);

alter table privado.aplicaciones_recibidas enable row level security;
revoke all on privado.aplicaciones_recibidas from public, anon, authenticated;

insert into privado.aplicaciones_recibidas (vacante_id, recibidas)
select a.vacante_id, count(*)::int
  from public.applications a
 group by a.vacante_id
on conflict (vacante_id) do update
    set recibidas = greatest(aplicaciones_recibidas.recibidas, excluded.recibidas);

-- `after insert`: con `on conflict do update`, como en `aplicar_a_vacante`, solo
-- dispara si la fila se insertó de verdad. Volver a aplicar no ocupa cupo.
create or replace function public.applications_cuenta_las_recibidas()
    returns trigger
    language plpgsql
    security definer
    set search_path = ''
as $$
declare
    v_recibidas int;
    v_limite int;
begin
    insert into privado.aplicaciones_recibidas as r (vacante_id, recibidas)
    values (new.vacante_id, 1)
    on conflict (vacante_id) do update set recibidas = r.recibidas + 1
    returning r.recibidas into v_recibidas;

    v_limite := public.limite_de_aplicaciones(new.empresa_id);
    if v_limite is not null and v_recibidas > v_limite then
        raise exception using
            errcode = 'PT409',
            message = 'la vacante ya no recibe aplicaciones',
            detail = format('%s de %s aplicaciones recibidas', v_limite, v_limite),
            hint = format('En el plan gratis cada vacante recibe hasta %s aplicaciones. Borrar o descartar no libera cupo.', v_limite);
    end if;
    return null;
end;
$$;

drop trigger if exists applications_cupo_del_plan on public.applications;
create trigger applications_cupo_del_plan
    after insert on public.applications
    for each row execute function public.applications_cuenta_las_recibidas();

-- Igual que en 0008, sin el conteo (ahora lo hace el trigger, para cualquier vía
-- de entrada) y con la oposición del candidato. Cambia la firma, así que se
-- borra la anterior: dos versiones serían una llamada ambigua para PostgREST.
drop function if exists public.aplicar_a_vacante(uuid, text, text, text, text, text);

create function public.aplicar_a_vacante(
        p_vacante_id uuid,
        p_full_name  text,
        p_email      text,
        p_cv_path    text default null,
        p_headline   text default null,
        p_linkedin   text default null,
        -- "Evaluar mi CV sin procesos automatizados" en el formulario.
        p_sin_ia     boolean default false
    )
    returns uuid
    language plpgsql
    security definer
    set search_path = ''
as $$
declare
    v_empresa     uuid;
    v_candidato   uuid;
    v_application uuid;
    v_email       text := lower(trim(p_email));
    v_name        text := trim(p_full_name);
begin
    select empresa_id into v_empresa
      from public.vacantes
     where id = p_vacante_id and status = 'open'
       for update;

    if v_empresa is null then
        raise exception using
            errcode = '22023',
            message = 'vacante no disponible';
    end if;

    if v_name = '' or length(v_name) > 200 then
        raise exception using errcode = '22023', message = 'nombre invalido';
    end if;

    if v_email !~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' then
        raise exception using errcode = '22023', message = 'email invalido';
    end if;

    if p_cv_path is not null
       and p_cv_path not like v_empresa::text || '/%' then
        raise exception using
            errcode = '22023',
            message = 'la ruta del CV no corresponde a la empresa de la vacante';
    end if;

    insert into public.candidatos
        (empresa_id, full_name, email, headline, linkedin_url, cv_url, source)
    values
        (v_empresa, v_name, v_email, p_headline, p_linkedin, p_cv_path, 'career-site')
    on conflict (empresa_id, email) do update
        set full_name    = excluded.full_name,
            headline     = coalesce(excluded.headline, candidatos.headline),
            linkedin_url = coalesce(excluded.linkedin_url, candidatos.linkedin_url),
            cv_url       = coalesce(excluded.cv_url, candidatos.cv_url),
            updated_at   = now()
    returning id into v_candidato;

    -- Volver a aplicar devuelve la misma application. La oposición se puede
    -- sumar al volver a aplicar, nunca quitar.
    insert into public.applications (empresa_id, vacante_id, candidato_id, status, sin_ia)
    values (v_empresa, p_vacante_id, v_candidato, 'applied', coalesce(p_sin_ia, false))
    on conflict (vacante_id, candidato_id) do update
        set sin_ia = applications.sin_ia or excluded.sin_ia
    returning id into v_application;

    return v_application;
end;
$$;

revoke execute on function public.aplicar_a_vacante(uuid, text, text, text, text, text, boolean)
    from public;
grant execute on function public.aplicar_a_vacante(uuid, text, text, text, text, text, boolean)
    to anon, authenticated;

-- `cupo_completo` sale del contador. Mismas columnas y en el mismo orden que 0008.
create or replace view public.vacantes_publicas
    with (security_invoker = false)
as
    select v.id, v.slug, v.title, v.jd, v.seniority, v.modality, v.location, v.created_at,
           e.name as empresa_nombre, e.slug as empresa_slug,
           case when v.salario_publico then v.salary_min end as salario_min,
           case when v.salario_publico then v.salary_max end as salario_max,
           case when v.salario_publico then v.currency end as moneda,
           coalesce(
               coalesce((select r.recibidas from privado.aplicaciones_recibidas r
                          where r.vacante_id = v.id), 0)
                   >= public.limite_de_aplicaciones(v.empresa_id),
               false
           ) as cupo_completo
      from public.vacantes v
      join public.empresas e on e.id = v.empresa_id
     where v.status = 'open';

grant select on public.vacantes_publicas to anon, authenticated;

-- "47 de 50" en el panel: lo da la base y no la UI (ADR-016). Las recibidas, no
-- las que quedan: es el número con el que corta el tope.
create or replace function public.cupos_de_aplicaciones()
    returns table (vacante_id uuid, recibidas int, limite int, completo boolean)
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select v.id,
           coalesce(r.recibidas, 0),
           public.limite_de_aplicaciones(v.empresa_id),
           coalesce(coalesce(r.recibidas, 0) >= public.limite_de_aplicaciones(v.empresa_id), false)
      from public.vacantes v
      left join privado.aplicaciones_recibidas r on r.vacante_id = v.id
     where v.empresa_id = public.empresa_id()
       and public.app_role() in ('HR', 'Director', 'SuperAdmin');
$$;

revoke execute on function public.cupos_de_aplicaciones() from public, anon;
grant execute on function public.cupos_de_aplicaciones() to authenticated;

-- ─── 7. El cockpit es del plan con IA ───────────────────────────────────────
--
-- Entrevistas, psicométricos y constancias no están en el plan gratis (ADR-017
-- §1). El panel no los muestra, pero la API los aceptaba. Solo se corta la
-- creación: si una empresa deja de pagar, lo que ya existía se puede terminar
-- (un candidato a medio test lo puede cerrar).
--
-- El nombre del trigger va después de `*_enforce_empresa` en orden alfabético:
-- cuando corre, el `empresa_id` ya viene de la aplicación.
create or replace function public.cockpit_solo_con_plan_ia()
    returns trigger
    language plpgsql
    security definer
    set search_path = ''
as $$
begin
    if (select e.plan from public.empresas e where e.id = new.empresa_id)
       is distinct from 'ia' then
        raise exception '% no está incluido en el plan gratis', tg_table_name
            using errcode = 'PT403',
                  hint = 'Entrevistas, psicométricos y constancias son parte de los servicios de IA.';
    end if;
    return new;
end;
$$;

drop trigger if exists psicometricos_solo_plan_ia on public.psicometricos;
create trigger psicometricos_solo_plan_ia
    before insert on public.psicometricos
    for each row execute function public.cockpit_solo_con_plan_ia();

drop trigger if exists entrevistas_solo_plan_ia on public.entrevistas;
create trigger entrevistas_solo_plan_ia
    before insert on public.entrevistas
    for each row execute function public.cockpit_solo_con_plan_ia();

drop trigger if exists constancias_solo_plan_ia on public.constancias;
create trigger constancias_solo_plan_ia
    before insert on public.constancias
    for each row execute function public.cockpit_solo_con_plan_ia();

-- ─── 8. Publicaciones: tantas como vacantes activas cada 30 días ────────────
--
-- El tope de 0008 es de vacantes activas: cerrar una y publicar otra dejaba usar
-- el plan gratis sin fin, de 3 en 3. LinkedIn corta igual su empleo gratis ("a
-- maximum of 1 free job at a time and a limited number of free jobs in a 30-day
-- window"). Aquí, en 30 días se publican tantas vacantes nuevas como vacantes
-- activas permite el plan. Reabrir una vacante no cuenta: sus aplicaciones
-- siguen sumando para su cupo de 50.
alter table public.vacantes add column if not exists publicada_en timestamptz;

update public.vacantes
   set publicada_en = created_at
 where publicada_en is null and status <> 'draft';

comment on column public.vacantes.publicada_en is
    'Primera vez que la vacante pasó a open. La fija la base: con ella se cuentan las publicaciones de los últimos 30 días (ADR-019).';

-- La empresa no la elige ni la mueve. Sin sesión de tenant (rol dueño o clave
-- secreta) Vector HR sí puede corregirla.
create or replace function public.vacantes_fecha_de_publicacion()
    returns trigger
    language plpgsql
    set search_path = ''
as $$
begin
    if public.empresa_id() is not null then
        new.publicada_en := case when tg_op = 'UPDATE' then old.publicada_en end;
    end if;
    if new.publicada_en is null and new.status = 'open' then
        new.publicada_en := now();
    end if;
    return new;
end;
$$;

-- Va antes que `vacantes_limite_del_plan` en orden alfabético: cuando el tope
-- corre, la fecha ya está puesta.
drop trigger if exists vacantes_fecha_de_publicacion on public.vacantes;
create trigger vacantes_fecha_de_publicacion
    before insert or update on public.vacantes
    for each row execute function public.vacantes_fecha_de_publicacion();

-- Igual que en 0008, más las publicaciones de los últimos 30 días.
create or replace function public.vacantes_respeta_limite_del_plan()
    returns trigger
    language plpgsql
    security definer
    set search_path = ''
as $$
declare
    v_limite    int;
    v_activas   int;
    v_recientes int;
begin
    if new.status <> 'open' or (tg_op = 'UPDATE' and old.status = 'open') then
        return new;
    end if;

    perform 1 from public.empresas where id = new.empresa_id for update;
    v_limite := public.limite_de_vacantes(new.empresa_id);
    if v_limite is null then
        return new;
    end if;

    select count(*) into v_activas
      from public.vacantes
     where empresa_id = new.empresa_id
       and status = 'open'
       and id <> new.id;

    if v_activas >= v_limite then
        raise exception using
            errcode = 'PT409',
            message = 'limite de vacantes del plan alcanzado',
            detail = format('%s de %s vacantes activas', v_activas, v_limite),
            hint = 'Elimina una vacante activa para publicar otra.';
    end if;

    -- Solo la primera publicación cuenta; reabrir no.
    if tg_op = 'INSERT' or old.publicada_en is null then
        select count(*) into v_recientes
          from public.vacantes
         where empresa_id = new.empresa_id
           and id <> new.id
           and publicada_en > now() - interval '30 days';

        if v_recientes >= v_limite then
            raise exception using
                errcode = 'PT409',
                message = 'limite de publicaciones del plan alcanzado',
                detail = format('%s de %s vacantes publicadas en los últimos 30 días',
                                v_recientes, v_limite),
                hint = 'En el plan gratis se publican cada 30 días tantas vacantes nuevas como vacantes activas permite el plan.';
        end if;
    end if;
    return new;
end;
$$;

-- "3 de 4" del panel, más las publicaciones. Cambian las columnas que devuelve,
-- así que se borra y se crea de nuevo. Arregla además el `libres` de 0008:
-- `greatest(0, null)` es 0, y el plan con IA salía con "0 libres" en vez de sin tope.
drop function if exists public.mi_cupo_de_vacantes();

create function public.mi_cupo_de_vacantes()
    returns table (
        activas int,
        limite int,
        libres int,
        max_aplicaciones int,
        publicaciones_libres int,
        proxima_publicacion timestamptz
    )
    language sql
    stable
    security definer
    set search_path = ''
as $$
    with e as (
        select public.empresa_id() as id,
               public.limite_de_vacantes(public.empresa_id()) as limite
    ),
    conteo as (
        select
            (select count(*)::int from public.vacantes v, e
              where v.empresa_id = e.id and v.status = 'open') as activas,
            (select count(*)::int from public.vacantes v, e
              where v.empresa_id = e.id
                and v.publicada_en > now() - interval '30 days') as recientes,
            (select pg_catalog.min(v.publicada_en) from public.vacantes v, e
              where v.empresa_id = e.id
                and v.publicada_en > now() - interval '30 days') as primera_reciente
    )
    select c.activas,
           e.limite,
           case when e.limite is not null then greatest(0, e.limite - c.activas) end,
           public.limite_de_aplicaciones(e.id),
           case when e.limite is not null then greatest(0, e.limite - c.recientes) end,
           -- Cuándo se libera la próxima, si ya no queda ninguna.
           case when c.recientes >= e.limite then c.primera_reciente + interval '30 days' end
      from e
      cross join conteo c
     where e.id is not null;
$$;

revoke execute on function public.mi_cupo_de_vacantes() from public, anon;
grant execute on function public.mi_cupo_de_vacantes() to authenticated;

-- Las funciones de trigger no se llaman a mano.
revoke execute on function public.vacantes_fecha_de_publicacion() from public, anon, authenticated;
revoke execute on function public.applications_oposicion_irrevocable() from public, anon, authenticated;
revoke execute on function public.empresas_al_contratar_borra_el_gancho() from public, anon, authenticated;
revoke execute on function public.applications_cuenta_las_recibidas() from public, anon, authenticated;
revoke execute on function public.cockpit_solo_con_plan_ia() from public, anon, authenticated;

commit;
