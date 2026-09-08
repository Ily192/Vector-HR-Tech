-- ════════════════════════════════════════════════════════════════════════════
-- Vortex Ops · 0004_security_hardening
-- Fecha: 2026-09-07
-- Cierra las vias de escalada multi-tenant encontradas en la auditoria de
-- seguridad previa al primer deploy.
-- Requiere: 0001_initial_schema.sql, 0002_hr_phase2.sql, 0003_auth_hooks.sql
-- ════════════════════════════════════════════════════════════════════════════
--
-- Contexto: ninguna de estas migraciones se habia aplicado nunca a un proyecto
-- real. La auditoria encontro que un usuario ANONIMO, con la anon key que es
-- publica por diseño, podia tomar control de cualquier tenant por tres vias
-- distintas. Dos se cerraron reescribiendo 0001 y 0003 en su sitio (helpers de
-- identidad y hook de signup). Las demas se cierran aqui.
--
-- Principio que guia el archivo: RLS es la SEGUNDA linea de defensa, no la
-- unica. Donde se puede, el privilegio se quita con revoke/grant y el acceso
-- publico pasa por funciones `security definer` de superficie estrecha, en
-- lugar de por policies que intentan expresar "conoce un secreto" —algo que
-- RLS no puede expresar, porque filtra filas, no conocimiento.
-- ════════════════════════════════════════════════════════════════════════════

begin;

-- ════════════════════════════════════════════════════════════════════════════
-- 1. SuperAdmin deja de ser un rol de tenant
-- ════════════════════════════════════════════════════════════════════════════
--
-- Antes: `role` vivia en `profiles` (por tenant) pero 'SuperAdmin' otorgaba
-- FOR ALL sobre TODAS las empresas. Y `profiles_hr_manage` dejaba que un HR
-- de un cliente promoviera a un complice a SuperAdmin dentro de su propio
-- tenant. Cadena completa: HR de un cliente → acceso global de lectura,
-- escritura y borrado sobre todos los demas clientes.
--
-- Ahora: el privilegio de plataforma vive en su propia tabla, que ningun
-- usuario `authenticated` puede escribir.

create table if not exists public.platform_admins (
    user_id uuid primary key references auth.users(id) on delete cascade,
    granted_at timestamptz not null default now(),
    note text
);

alter table public.platform_admins enable row level security;
alter table public.platform_admins force row level security;

-- Sin policies de escritura a proposito: solo `service_role` (BYPASSRLS) o el
-- superusuario pueden dar de alta un admin de plataforma.
drop policy if exists platform_admins_self_read on public.platform_admins;
create policy platform_admins_self_read on public.platform_admins
    for select using (user_id = (select auth.uid()));

revoke all on public.platform_admins from anon, authenticated;
grant select on public.platform_admins to authenticated;

create or replace function public.is_platform_admin() returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select exists (
        select 1 from public.platform_admins where user_id = auth.uid()
    );
$$;

revoke execute on function public.is_platform_admin() from public, anon;
grant execute on function public.is_platform_admin() to authenticated;

drop policy if exists empresas_superadmin_all on public.empresas;
drop policy if exists empresas_platform_admin_all on public.empresas;
create policy empresas_platform_admin_all on public.empresas
    for all
    using ((select public.is_platform_admin()))
    with check ((select public.is_platform_admin()));

-- ════════════════════════════════════════════════════════════════════════════
-- 2. profiles: cerrar la auto-promocion
-- ════════════════════════════════════════════════════════════════════════════
--
-- Antes: `profiles_self_update ... for update using (id = auth.uid())` sin
-- WITH CHECK. El check heredado solo exigia que la fila siguiera siendo la
-- propia, asi que esto pasaba sin problema:
--
--     update profiles set role = 'SuperAdmin' where id = auth.uid();
--     update profiles set empresa_id = '<otro tenant>' where id = auth.uid();
--
-- RLS no tiene granularidad de columna, asi que el WITH CHECK se apoya en un
-- trigger para congelar las columnas privilegiadas.

create or replace function public.profiles_freeze_privileged_columns()
    returns trigger
    language plpgsql
    security definer
    set search_path = ''
as $$
begin
    -- service_role y el owner pueden cambiar rol/empresa (alta y soporte).
    if current_setting('request.jwt.claims', true) is null then
        return new;
    end if;

    if new.role is distinct from old.role then
        if not (public.app_role() in ('HR', 'Director')
                and new.role <> 'SuperAdmin'
                and new.empresa_id = public.empresa_id()
                and old.id <> auth.uid()) then
            raise exception using
                errcode = '42501',
                message = 'no puedes cambiar tu propio rol ni otorgar SuperAdmin';
        end if;
    end if;

    if new.empresa_id is distinct from old.empresa_id then
        raise exception using
            errcode = '42501',
            message = 'empresa_id de un profile es inmutable';
    end if;

    return new;
end;
$$;

drop trigger if exists profiles_freeze_privileged on public.profiles;
create trigger profiles_freeze_privileged
    before update on public.profiles
    for each row execute function public.profiles_freeze_privileged_columns();

drop policy if exists profiles_self_update on public.profiles;
create policy profiles_self_update on public.profiles
    for update
    using (id = (select auth.uid()))
    with check (id = (select auth.uid()));

-- HR/Director gestionan su tenant, pero no reparten SuperAdmin.
drop policy if exists profiles_hr_manage on public.profiles;
create policy profiles_hr_manage on public.profiles
    for all
    using (
        empresa_id = (select public.empresa_id())
        and (select public.app_role()) in ('HR', 'Director')
    )
    with check (
        empresa_id = (select public.empresa_id())
        and (select public.app_role()) in ('HR', 'Director')
        and role <> 'SuperAdmin'
    );

-- ════════════════════════════════════════════════════════════════════════════
-- 3. psicometricos: quitar el acceso anonimo directo a la tabla
-- ════════════════════════════════════════════════════════════════════════════
--
-- Antes habia dos policies publicas y ambas eran explotables:
--
--   · `psicometricos_public_token_read` se llamaba "por token" pero el
--     predicado NO mencionaba el token. Cualquiera con la anon key hacia
--     `select token, raw_answers, report_summary from psicometricos` y se
--     llevaba TODOS los tests activos de TODOS los tenants, con los tokens en
--     claro — es decir, podia completar el test de cualquier candidato.
--
--   · `psicometricos_public_token_update` tenia un WITH CHECK
--     (`status in ('in_progress','completed')`) mas debil que su USING. Eso
--     permitia a un anonimo reescribir `empresa_id`, `token`, `expires_at` y
--     los cinco Big5 de cualquier fila pendiente de cualquier tenant.
--
-- RLS no puede expresar "el cliente conoce este secreto". El flujo publico
-- pasa ahora por dos funciones `security definer` de superficie minima.

-- Token hasheado en reposo: un dump de la tabla ya no permite suplantar.
alter table public.psicometricos add column if not exists token_hash text;

update public.psicometricos
   set token_hash = encode(sha256(token::bytea), 'hex')
 where token_hash is null;

alter table public.psicometricos alter column token_hash set not null;

create unique index if not exists psicometricos_token_hash_key
    on public.psicometricos(token_hash);

drop index if exists psicometricos_token_idx;
alter table public.psicometricos drop column if exists token;

drop policy if exists psicometricos_public_token_read on public.psicometricos;
drop policy if exists psicometricos_public_token_update on public.psicometricos;

revoke all on public.psicometricos from anon;

-- Lectura publica por token: devuelve SOLO lo que el candidato necesita para
-- responder. Nunca empresa_id, ni el hash, ni resultados de terceros.
create or replace function public.get_psicometrico_by_token(p_token text)
    returns table (
        id uuid,
        status psicometrico_status,
        started_at timestamptz,
        expires_at timestamptz
    )
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select p.id, p.status, p.started_at, p.expires_at
      from public.psicometricos p
     where p.token_hash = encode(sha256(p_token::bytea), 'hex')
       and p.status in ('pending', 'in_progress')
       and p.expires_at > now();
$$;

-- Escritura publica por token: solo las columnas de respuesta. `empresa_id`,
-- `application_id`, `token_hash` y `expires_at` quedan fuera de alcance.
create or replace function public.submit_psicometrico(
        p_token   text,
        p_answers jsonb,
        p_big5    jsonb default null,
        p_finish  boolean default false
    )
    returns uuid
    language plpgsql
    security definer
    set search_path = ''
as $$
declare
    target public.psicometricos%rowtype;
begin
    select * into target
      from public.psicometricos
     where token_hash = encode(sha256(p_token::bytea), 'hex')
       and status in ('pending', 'in_progress')
       and expires_at > now()
     for update;

    if not found then
        raise exception using
            errcode = '22023',
            message = 'token invalido, ya usado o expirado';
    end if;

    update public.psicometricos
       set raw_answers = coalesce(p_answers, raw_answers),
           big5_openness = coalesce((p_big5 ->> 'openness')::numeric, big5_openness),
           big5_conscientiousness = coalesce((p_big5 ->> 'conscientiousness')::numeric, big5_conscientiousness),
           big5_extraversion = coalesce((p_big5 ->> 'extraversion')::numeric, big5_extraversion),
           big5_agreeableness = coalesce((p_big5 ->> 'agreeableness')::numeric, big5_agreeableness),
           big5_neuroticism = coalesce((p_big5 ->> 'neuroticism')::numeric, big5_neuroticism),
           started_at = coalesce(started_at, now()),
           status = case when p_finish then 'completed'::psicometrico_status
                         else 'in_progress'::psicometrico_status end,
           completed_at = case when p_finish then now() else completed_at end,
           updated_at = now()
     where id = target.id;

    return target.id;
end;
$$;

revoke execute on function public.get_psicometrico_by_token(text) from public;
revoke execute on function public.submit_psicometrico(text, jsonb, jsonb, boolean) from public;
grant execute on function public.get_psicometrico_by_token(text) to anon, authenticated;
grant execute on function public.submit_psicometrico(text, jsonb, jsonb, boolean) to anon, authenticated;

-- ════════════════════════════════════════════════════════════════════════════
-- 4. vacantes: el career-site no necesita ver el ICP ni las bandas salariales
-- ════════════════════════════════════════════════════════════════════════════
--
-- `vacantes_public_open_read` daba SELECT a `anon` sobre la tabla entera. RLS
-- filtra filas, no columnas, asi que cualquiera se llevaba de todos los
-- tenants el `icp_text` (el perfil ideal interno), el `icp_embedding` y
-- `salary_min`/`salary_max`. Para un SaaS B2B cuyos clientes compiten entre
-- si, eso es fuga comercial directa.

drop policy if exists vacantes_public_open_read on public.vacantes;
revoke all on public.vacantes from anon;

create or replace view public.vacantes_publicas
with (security_invoker = false) as
    select id, empresa_id, slug, title, jd, seniority, modality, location,
           created_at
      from public.vacantes
     where status = 'open';

grant select on public.vacantes_publicas to anon, authenticated;

-- ════════════════════════════════════════════════════════════════════════════
-- 5. Integridad de tenant compuesta
-- ════════════════════════════════════════════════════════════════════════════
--
-- Las FK a `vacantes`/`candidatos` se verifican con un scan interno que IGNORA
-- RLS. Un HR del tenant A podia insertar una application con su propio
-- empresa_id pero un candidato_id del tenant B; el insert pasaba, y cualquier
-- worker con service_role hacia el join y exponia datos del tenant B.
-- La FK compuesta hace que el propio motor lo impida, tambien para service_role.

alter table public.vacantes   drop constraint if exists vacantes_id_empresa_uk;
alter table public.vacantes   add  constraint vacantes_id_empresa_uk   unique (id, empresa_id);
alter table public.candidatos drop constraint if exists candidatos_id_empresa_uk;
alter table public.candidatos add  constraint candidatos_id_empresa_uk unique (id, empresa_id);
alter table public.applications drop constraint if exists applications_id_empresa_uk;
alter table public.applications add  constraint applications_id_empresa_uk unique (id, empresa_id);

alter table public.applications drop constraint if exists applications_vacante_id_fkey;
alter table public.applications add  constraint applications_vacante_fk
    foreign key (vacante_id, empresa_id)
    references public.vacantes(id, empresa_id) on delete cascade;

alter table public.applications drop constraint if exists applications_candidato_id_fkey;
alter table public.applications add  constraint applications_candidato_fk
    foreign key (candidato_id, empresa_id)
    references public.candidatos(id, empresa_id) on delete cascade;

alter table public.psicometricos drop constraint if exists psicometricos_application_id_fkey;
alter table public.psicometricos add  constraint psicometricos_application_fk
    foreign key (application_id, empresa_id)
    references public.applications(id, empresa_id) on delete cascade;

alter table public.entrevistas drop constraint if exists entrevistas_application_id_fkey;
alter table public.entrevistas add  constraint entrevistas_application_fk
    foreign key (application_id, empresa_id)
    references public.applications(id, empresa_id) on delete cascade;

alter table public.profiles drop constraint if exists profiles_id_empresa_uk;
alter table public.profiles add  constraint profiles_id_empresa_uk unique (id, empresa_id);

alter table public.constancias drop constraint if exists constancias_profile_id_fkey;
alter table public.constancias add  constraint constancias_profile_fk
    foreign key (profile_id, empresa_id)
    references public.profiles(id, empresa_id) on delete cascade;

-- El guard anti tenant-drift solo estaba en INSERT, asi que un UPDATE podia
-- mover una fila a otro tenant.
drop trigger if exists psicometricos_enforce_empresa_update on public.psicometricos;
create trigger psicometricos_enforce_empresa_update
    before update on public.psicometricos
    for each row execute function public.enforce_empresa_id_from_application();

drop trigger if exists entrevistas_enforce_empresa_update on public.entrevistas;
create trigger entrevistas_enforce_empresa_update
    before update on public.entrevistas
    for each row execute function public.enforce_empresa_id_from_application();

-- ════════════════════════════════════════════════════════════════════════════
-- 6. Scoping por rol en las tablas con PII
-- ════════════════════════════════════════════════════════════════════════════
--
-- `candidatos`, `applications` y `entrevistas` tenian `for all using
-- (empresa_id = auth.empresa_id())` sin ningun filtro de rol. Un Colaborador
-- —o un usuario con rol `cliente`— tenia SELECT/INSERT/UPDATE/DELETE sobre
-- toda la base de candidatos con su PII, y el DELETE cascadeaba: cualquier
-- colaborador podia borrar el pipeline entero del tenant.

drop policy if exists candidatos_tenant_isolation on public.candidatos;
drop policy if exists candidatos_tenant_read on public.candidatos;
create policy candidatos_tenant_read on public.candidatos
    for select using (
        empresa_id = (select public.empresa_id())
        and (select public.app_role()) in ('HR', 'Director', 'SuperAdmin')
    );
drop policy if exists candidatos_tenant_write on public.candidatos;
create policy candidatos_tenant_write on public.candidatos
    for all
    using (
        empresa_id = (select public.empresa_id())
        and (select public.app_role()) in ('HR', 'Director')
    )
    with check (
        empresa_id = (select public.empresa_id())
        and (select public.app_role()) in ('HR', 'Director')
    );

drop policy if exists applications_tenant_isolation on public.applications;
drop policy if exists applications_tenant_read on public.applications;
create policy applications_tenant_read on public.applications
    for select using (
        empresa_id = (select public.empresa_id())
        and (select public.app_role()) in ('HR', 'Director', 'SuperAdmin')
    );
drop policy if exists applications_tenant_write on public.applications;
create policy applications_tenant_write on public.applications
    for all
    using (
        empresa_id = (select public.empresa_id())
        and (select public.app_role()) in ('HR', 'Director')
    )
    with check (
        empresa_id = (select public.empresa_id())
        and (select public.app_role()) in ('HR', 'Director')
    );

drop policy if exists entrevistas_tenant_isolation on public.entrevistas;
drop policy if exists entrevistas_tenant_read on public.entrevistas;
create policy entrevistas_tenant_read on public.entrevistas
    for select using (
        empresa_id = (select public.empresa_id())
        and (
            (select public.app_role()) in ('HR', 'Director', 'SuperAdmin')
            or interviewer_id = (select auth.uid())
        )
    );
drop policy if exists entrevistas_tenant_write on public.entrevistas;
create policy entrevistas_tenant_write on public.entrevistas
    for all
    using (
        empresa_id = (select public.empresa_id())
        and (select public.app_role()) in ('HR', 'Director')
    )
    with check (
        empresa_id = (select public.empresa_id())
        and (select public.app_role()) in ('HR', 'Director')
    );

-- ════════════════════════════════════════════════════════════════════════════
-- 7. runs: el UPDATE del worker afectaba 0 filas en silencio
-- ════════════════════════════════════════════════════════════════════════════
--
-- Solo existia una policy de SELECT. El worker corre como `authenticated`
-- (set local role), asi que su `update runs set status=...` no matcheaba
-- ninguna fila y no lanzaba error: el cost tracking y el estado de los runs
-- nunca se persistian.

drop policy if exists runs_tenant_isolation on public.runs;
drop policy if exists runs_tenant_read on public.runs;
create policy runs_tenant_read on public.runs
    for select using (empresa_id = (select public.empresa_id()));

drop policy if exists runs_tenant_write on public.runs;
create policy runs_tenant_write on public.runs
    for all
    using (empresa_id = (select public.empresa_id()))
    with check (empresa_id = (select public.empresa_id()));

-- ════════════════════════════════════════════════════════════════════════════
-- 8. activity_log: la inmutabilidad se evitaba con TRUNCATE
-- ════════════════════════════════════════════════════════════════════════════
--
-- Los triggers de inmutabilidad son FOR EACH ROW, y TRUNCATE no dispara
-- triggers de fila. Un `truncate activity_log` borraba el log de auditoria
-- entero sin tocar ninguna barrera.

create or replace function public.activity_log_no_truncate() returns trigger
    language plpgsql
as $$
begin
    raise exception 'activity_log is append-only; TRUNCATE forbidden';
end;
$$;

drop trigger if exists activity_log_no_truncate on public.activity_log;
create trigger activity_log_no_truncate
    before truncate on public.activity_log
    for each statement execute function public.activity_log_no_truncate();

revoke truncate on public.activity_log from anon, authenticated;

-- El log lo escribe el backend; los usuarios solo leen el de su tenant.
drop policy if exists activity_log_tenant_insert on public.activity_log;
create policy activity_log_tenant_insert on public.activity_log
    for insert with check (empresa_id = (select public.empresa_id()));

-- ════════════════════════════════════════════════════════════════════════════
-- 9. FORCE ROW LEVEL SECURITY en las tablas con PII
-- ════════════════════════════════════════════════════════════════════════════
--
-- Sin FORCE, el owner de la tabla (`postgres`) ignora RLS. El worker de
-- hr-engine se conecta con el owner y hace `set local role authenticated`
-- como primera sentencia — correcto, pero si un worker futuro olvida esa
-- llamada, corre sin ninguna barrera y en silencio. Con FORCE, ese olvido
-- falla de forma ruidosa en vez de filtrar datos entre tenants.
--
-- Nota: `service_role` tiene el atributo BYPASSRLS, que FORCE no anula. Sigue
-- siendo un privilegio de blast radius total y debe tratarse como tal.

alter table public.empresas      force row level security;
alter table public.profiles      force row level security;
alter table public.vacantes      force row level security;
alter table public.candidatos    force row level security;
alter table public.applications  force row level security;
alter table public.runs          force row level security;
alter table public.psicometricos force row level security;
alter table public.entrevistas   force row level security;
alter table public.constancias   force row level security;

-- ════════════════════════════════════════════════════════════════════════════
-- 10. Indices compuestos por tenant
-- ════════════════════════════════════════════════════════════════════════════
--
-- Todas las queries reales son `where empresa_id = X and <filtro>`, pero cada
-- indice era de una sola columna.

create index if not exists vacantes_empresa_status_idx
    on public.vacantes(empresa_id, status);
create index if not exists applications_empresa_status_idx
    on public.applications(empresa_id, status);
create index if not exists applications_vacante_score_idx
    on public.applications(vacante_id, fit_score desc nulls last);
create index if not exists candidatos_empresa_created_idx
    on public.candidatos(empresa_id, created_at desc);
create index if not exists runs_empresa_started_idx
    on public.runs(empresa_id, started_at desc);

commit;
