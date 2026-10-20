-- ════════════════════════════════════════════════════════════════════════════
-- Vortex Ops · 0014_evaluacion_ia_del_plan_de_pago
-- Fecha: 2026-10-20
-- La evaluación con IA del plan de pago, como trabajo interno del hr-engine (ADR-021).
-- Requiere: 0001..0013
-- ════════════════════════════════════════════════════════════════════════════
--
-- Un barrido de Celery beat evalúa cada aplicación de una empresa `ia` con el
-- texto de su CV, anonimizado, una sola vez. Esta migración le da al barrido
-- dónde llevar la cuenta y a la empresa lo que necesita ver:
--
--   · `privado.evaluaciones_ia`: los intentos, el reclamo y la fecha de cada
--     evaluación. El barrido reclama con `for update skip locked`. Tras 3
--     intentos sin éxito la aplicación queda "sin evaluar" para revisarla a mano.
--   · `empresas.ia_cvs_por_mes`: el tope de seguridad por empresa (1.000 por
--     defecto). No es la bolsa comercial del plan (ADR-018 §13).
--   · `applications.fit_strengths` y `evaluada_en`: las fortalezas que el
--     contrato ya traía y cuándo se evaluó.
--   · La oposición del candidato también devuelve a "Aplicados" lo que evaluó
--     la IA y borra su registro.
--   · `vacantes_publicas.evalua_con_ia`: el career site muestra el aviso que toca.
--   · `resumen_de_evaluaciones()`: para el panel, cuántas evaluó, cuántas
--     esperan, cuántas no se pudieron evaluar y cuántos CVs son ilegibles.
--
-- Las reglas viven en `services/hr-engine/app/domain/` (`anonimizacion.py` y
-- `evaluacion_ia.py`); `MAX_INTENTOS` es el mismo número que se usa aquí.
-- ════════════════════════════════════════════════════════════════════════════

begin;

-- ─── 1. El tope por empresa y lo que se guarda de la evaluación ─────────────

-- `empresas` no tiene política de escritura para las empresas: solo la cambian
-- Vector HR y el rol dueño, igual que `plan` y `limite_vacantes`.
alter table public.empresas
    add column if not exists ia_cvs_por_mes int not null default 1000
        check (ia_cvs_por_mes >= 0);

comment on column public.empresas.ia_cvs_por_mes is
    'Tope de seguridad de CVs evaluados con IA al mes (ADR-021 §6). Al llegar, las aplicaciones nuevas esperan al mes siguiente. No es la bolsa del plan.';

alter table public.applications
    add column if not exists fit_strengths text[] not null default '{}',
    add column if not exists evaluada_en timestamptz;

comment on column public.applications.evaluada_en is
    'Cuándo la evaluó la IA del plan de pago (ADR-021). Null si no se ha evaluado o si el candidato se opuso.';

-- ─── 2. La cuenta del barrido, fuera de la API ──────────────────────────────

create table if not exists privado.evaluaciones_ia (
    application_id uuid primary key references public.applications(id) on delete cascade,
    empresa_id uuid not null references public.empresas(id) on delete cascade,
    -- Sube al reclamar: un CV que tumbe el proceso no se reintenta sin fin.
    intentos int not null default 0 check (intentos >= 0),
    reclamada_en timestamptz,
    evaluada_en timestamptz,
    ultimo_error text
);

create index if not exists evaluaciones_ia_empresa_mes_idx
    on privado.evaluaciones_ia (empresa_id, evaluada_en);

alter table privado.evaluaciones_ia enable row level security;
revoke all on privado.evaluaciones_ia from public, anon, authenticated;

-- ─── 3. La oposición del candidato alcanza a lo evaluado ────────────────────

create or replace function public.applications_oposicion_a_la_ia()
    returns trigger
    language plpgsql
    security definer
    set search_path = ''
as $$
begin
    delete from privado.coincidencias where application_id = new.id;
    delete from privado.evaluaciones_ia where application_id = new.id;
    new.fit_score := null;
    new.fit_rationale := null;
    new.fit_gaps := '{}';
    new.fit_strengths := '{}';
    new.evaluada_en := null;
    -- La IA la había pasado a "Evaluados": vuelve a "Aplicados". Si una persona ya
    -- la movió a otra etapa, se queda donde está.
    if new.status = 'evaluated' then
        new.status := 'applied';
    end if;
    return new;
end;
$$;

revoke execute on function public.applications_oposicion_a_la_ia() from public, anon, authenticated;

-- ─── 4. El aviso del career site depende del plan ───────────────────────────

-- La columna nueva va al final: `create or replace view` solo deja agregar ahí.
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
           ) as cupo_completo,
           -- El candidato tiene derecho a saber si lo evalúa una IA; el plan no se expone.
           e.plan = 'ia' as evalua_con_ia
      from public.vacantes v
      join public.empresas e on e.id = v.empresa_id
     where v.status = 'open';

grant select on public.vacantes_publicas to anon, authenticated;

-- ─── 5. Lo que el panel muestra de las evaluaciones ─────────────────────────

-- Solo para empresas `ia` y para HR, Dirección o SuperAdmin de la empresa de la
-- vacante: a cualquier otro le devuelve cero filas.
create or replace function public.resumen_de_evaluaciones(p_vacante uuid)
    returns table (
        aplicaciones int,
        evaluadas int,
        en_espera int,
        sin_evaluar int,
        ilegibles int,
        sin_ia int
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
           and e.plan = 'ia'
    )
    select count(a.id)::int,
           count(a.id) filter (where a.fit_score is not null)::int,
           -- Las que el barrido todavía va a tomar: las que una persona ya movió de
           -- "Aplicados" no se evalúan.
           count(a.id) filter (
               where a.status = 'applied' and a.fit_score is null and not a.sin_ia
                 and c.cv_url is not null and i.application_id is null
                 and coalesce(ev.intentos, 0) < 3
           )::int,
           count(a.id) filter (
               where a.fit_score is null and not a.sin_ia and i.application_id is null
                 and coalesce(ev.intentos, 0) >= 3
           )::int,
           count(i.application_id)::int,
           count(a.id) filter (where a.sin_ia)::int
      from vacante
      left join public.applications a on a.vacante_id = vacante.id
      left join public.candidatos c on c.id = a.candidato_id
      left join privado.cvs_ilegibles i on i.application_id = a.id
      left join privado.evaluaciones_ia ev on ev.application_id = a.id
     group by vacante.id;
$$;

revoke execute on function public.resumen_de_evaluaciones(uuid) from public, anon;
grant execute on function public.resumen_de_evaluaciones(uuid) to authenticated;

commit;
