-- ════════════════════════════════════════════════════════════════════════════
-- Vortex Ops · 0008_plan_gratis_limites
-- Fecha: 2026-10-19
-- Límites del plan gratuito del career site (ADR-017, punto 3).
-- Requiere: 0001..0007
-- ════════════════════════════════════════════════════════════════════════════
--
-- La dueña de la regla es `services/hr-engine/app/domain/plan.py`, y su
-- contrato es `packages/types/contracts/limites-plan.json`. Aquí se aplica en
-- la base porque el panel de la empresa escribe sus vacantes con su sesión de
-- Supabase y el career site aplica con la anon key: ninguno de los dos pasa por
-- el hr-engine. Es defensa en profundidad (ADR-004). Los tests de seguridad
-- comprueban que esta copia y el contrato digan lo mismo.
--
--   · Vacantes activas: 3 hasta 50 personas, 4 desde 51; sin tamaño, 3.
--     Vector HR puede fijar otro número por empresa (`limite_vacantes`).
--   · Aplicaciones: 50 por vacante.
--   · El plan con IA no tiene estos topes.
--
-- Al pasarse de un tope se lanza SQLSTATE `PT409`: PostgREST responde 409
-- Conflict con el mensaje tal cual (docs.postgrest.org, "Errors" →
-- "Raise errors with HTTP Status Codes").
--
-- Eliminar una vacante es borrado lógico: `status = 'closed'` y `deleted_at`.
-- Las aplicaciones y la trazabilidad se conservan, y el cupo se libera.
-- ════════════════════════════════════════════════════════════════════════════

begin;

-- ─── Plan de la empresa ─────────────────────────────────────────────────────

do $$ begin
    create type plan_empresa as enum ('gratis', 'ia');
exception when duplicate_object then null; end $$;

-- Las empresas que ya existen entran como gratuitas: el plan con IA se activa
-- a mano cuando hay contrato (`update empresas set plan = 'ia' ...`).
alter table public.empresas
    add column if not exists plan plan_empresa not null default 'gratis',
    add column if not exists tamano_empleados int
        check (tamano_empleados is null or tamano_empleados > 0),
    add column if not exists limite_vacantes int
        check (limite_vacantes is null or limite_vacantes between 1 and 50);

comment on column public.empresas.limite_vacantes is
    'Ajuste de Vector HR al tope de vacantes activas. NULL = el que da el tamaño.';

alter table public.vacantes
    add column if not exists deleted_at timestamptz;

-- ─── La regla, en SQL ───────────────────────────────────────────────────────

-- Tope de vacantes activas de una empresa. NULL = sin tope (plan con IA).
create or replace function public.limite_de_vacantes(p_empresa_id uuid)
    returns int
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select case
        when e.plan = 'ia' then null
        else coalesce(
            e.limite_vacantes,
            case when coalesce(e.tamano_empleados, 0) >= 51 then 4 else 3 end
        )
    end
    from public.empresas e
    where e.id = p_empresa_id;
$$;

-- Tope de aplicaciones por vacante. NULL = sin tope (plan con IA).
create or replace function public.limite_de_aplicaciones(p_empresa_id uuid)
    returns int
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select case when e.plan = 'ia' then null else 50 end
    from public.empresas e
    where e.id = p_empresa_id;
$$;

-- La vista pública llama a `limite_de_aplicaciones` con los permisos de quien la
-- consulta (PostgreSQL, CREATE VIEW: "the user of a view must have permissions to
-- call all functions used by the view"). Solo devuelven un número por empresa.
revoke execute on function public.limite_de_vacantes(uuid) from public;
revoke execute on function public.limite_de_aplicaciones(uuid) from public;
grant execute on function public.limite_de_vacantes(uuid) to authenticated;
grant execute on function public.limite_de_aplicaciones(uuid) to anon, authenticated;

-- ─── Tope de vacantes activas: trigger ──────────────────────────────────────
--
-- Corre cuando una vacante pasa a 'open' (al crearla o al reabrirla). Bloquea la
-- fila de la empresa para que dos publicaciones simultáneas no pasen las dos
-- con el último cupo libre.
create or replace function public.vacantes_respeta_limite_del_plan()
    returns trigger
    language plpgsql
    security definer
    set search_path = ''
as $$
declare
    v_limite  int;
    v_activas int;
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
    return new;
end;
$$;

drop trigger if exists vacantes_limite_del_plan on public.vacantes;
create trigger vacantes_limite_del_plan
    before insert or update of status on public.vacantes
    for each row execute function public.vacantes_respeta_limite_del_plan();

-- Al cerrar una vacante se marca `deleted_at` si no lo trae: "Eliminar" en el
-- panel es solo `update ... set status = 'closed'`. Si se reabre, se limpia.
create or replace function public.vacantes_marca_borrado_logico()
    returns trigger
    language plpgsql
    set search_path = ''
as $$
begin
    if new.status = 'closed' and old.status <> 'closed' then
        new.closed_at := coalesce(new.closed_at, now());
        new.deleted_at := coalesce(new.deleted_at, now());
    elsif new.status = 'open' and old.status = 'closed' then
        new.deleted_at := null;
    end if;
    return new;
end;
$$;

drop trigger if exists vacantes_borrado_logico on public.vacantes;
create trigger vacantes_borrado_logico
    before update of status on public.vacantes
    for each row execute function public.vacantes_marca_borrado_logico();

-- ─── Tope de aplicaciones: dentro de aplicar_a_vacante ──────────────────────
--
-- Igual que en 0005, más el tope. Se bloquea la fila de la vacante para contar
-- sin carreras. Volver a aplicar a la misma vacante sigue devolviendo la misma
-- application aunque el cupo esté lleno: no es una aplicación nueva.
create or replace function public.aplicar_a_vacante(
        p_vacante_id uuid,
        p_full_name  text,
        p_email      text,
        p_cv_path    text default null,
        p_headline   text default null,
        p_linkedin   text default null
    )
    returns uuid
    language plpgsql
    security definer
    set search_path = ''
as $$
declare
    v_empresa      uuid;
    v_candidato    uuid;
    v_application  uuid;
    v_limite       int;
    v_aplicaciones int;
    v_email        text := lower(trim(p_email));
    v_name         text := trim(p_full_name);
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

    -- ¿Ya había aplicado? Entonces no ocupa cupo nuevo.
    select a.id into v_application
      from public.applications a
      join public.candidatos c on c.id = a.candidato_id
     where a.vacante_id = p_vacante_id
       and c.empresa_id = v_empresa
       and c.email = v_email;

    if v_application is null then
        v_limite := public.limite_de_aplicaciones(v_empresa);
        if v_limite is not null then
            select count(*) into v_aplicaciones
              from public.applications
             where vacante_id = p_vacante_id;
            if v_aplicaciones >= v_limite then
                raise exception using
                    errcode = 'PT409',
                    message = 'la vacante ya no recibe aplicaciones';
            end if;
        end if;
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

    insert into public.applications (empresa_id, vacante_id, candidato_id, status)
    values (v_empresa, p_vacante_id, v_candidato, 'applied')
    on conflict (vacante_id, candidato_id) do update
        set status = applications.status  -- no-op: solo para obtener el returning
    returning id into v_application;

    return v_application;
end;
$$;

revoke execute on function public.aplicar_a_vacante(uuid, text, text, text, text, text)
    from public;
grant execute on function public.aplicar_a_vacante(uuid, text, text, text, text, text)
    to anon, authenticated;

-- ─── Cupo de la empresa de la sesión ────────────────────────────────────────
--
-- Lo que el panel muestra como "3 de 4": lo calcula la base, no la UI (ADR-016).
create or replace function public.mi_cupo_de_vacantes()
    returns table (activas int, limite int, libres int, max_aplicaciones int)
    language sql
    stable
    security definer
    set search_path = ''
as $$
    with e as (select public.empresa_id() as id)
    select
        (select count(*)::int from public.vacantes v
          where v.empresa_id = e.id and v.status = 'open') as activas,
        public.limite_de_vacantes(e.id) as limite,
        greatest(0, public.limite_de_vacantes(e.id) - (
            select count(*)::int from public.vacantes v
             where v.empresa_id = e.id and v.status = 'open')) as libres,
        public.limite_de_aplicaciones(e.id) as max_aplicaciones
    from e
    where e.id is not null;
$$;

revoke execute on function public.mi_cupo_de_vacantes() from public, anon;
grant execute on function public.mi_cupo_de_vacantes() to authenticated;

-- ─── vacantes_publicas: cupo completo ───────────────────────────────────────
--
-- `create or replace view` solo deja añadir columnas al final: las de 0007 se
-- quedan igual y en el mismo orden.
create or replace view public.vacantes_publicas
    with (security_invoker = false)
as
    select v.id, v.slug, v.title, v.jd, v.seniority, v.modality, v.location, v.created_at,
           e.name as empresa_nombre, e.slug as empresa_slug,
           case when v.salario_publico then v.salary_min end as salario_min,
           case when v.salario_publico then v.salary_max end as salario_max,
           case when v.salario_publico then v.currency end as moneda,
           coalesce(
               (select count(*) from public.applications a where a.vacante_id = v.id)
                   >= public.limite_de_aplicaciones(v.empresa_id),
               false
           ) as cupo_completo
      from public.vacantes v
      join public.empresas e on e.id = v.empresa_id
     where v.status = 'open';

grant select on public.vacantes_publicas to anon, authenticated;

-- ─── JWT: plan y módulos ────────────────────────────────────────────────────
--
-- Como en 0003, más `plan` y `modulos` bajo `app_metadata` (ADR-015, ADR-017
-- punto 7). Los módulos por plan son los de `domain/plan.py`. Supabase exige
-- conservar los claims obligatorios (iss, aud, exp, sub, role…): solo se toca
-- `app_metadata`.
create or replace function public.custom_access_token_hook(event jsonb)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    user_id uuid := (event ->> 'user_id')::uuid;
    claims jsonb := coalesce(event -> 'claims', '{}'::jsonb);
    app_meta jsonb := coalesce(claims -> 'app_metadata', '{}'::jsonb);
    profile_empresa uuid;
    profile_role text;
    empresa_plan text;
begin
    select p.empresa_id, p.role::text, e.plan::text
        into profile_empresa, profile_role, empresa_plan
        from public.profiles p
        left join public.empresas e on e.id = p.empresa_id
        where p.id = user_id;

    if profile_empresa is not null then
        app_meta := jsonb_set(app_meta, '{empresa_id}',
                              to_jsonb(profile_empresa::text));
    end if;
    if profile_role is not null then
        app_meta := jsonb_set(app_meta, '{app_role}', to_jsonb(profile_role));
    end if;
    if empresa_plan is not null then
        app_meta := jsonb_set(app_meta, '{plan}', to_jsonb(empresa_plan));
        app_meta := jsonb_set(app_meta, '{modulos}', case empresa_plan
            when 'ia' then '["career-site", "cockpit"]'::jsonb
            else '["career-site"]'::jsonb
        end);
    end if;

    claims := jsonb_set(claims, '{app_metadata}', app_meta);
    return jsonb_set(event, '{claims}', claims);
end;
$$;

grant execute on function public.custom_access_token_hook(jsonb) to supabase_auth_admin;
grant select on public.empresas to supabase_auth_admin;
revoke execute on function public.custom_access_token_hook(jsonb) from authenticated, anon, public;

commit;
