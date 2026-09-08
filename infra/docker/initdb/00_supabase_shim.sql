-- ════════════════════════════════════════════════════════════════════════════
-- Shim de Supabase para el Postgres plano de desarrollo local.
-- ════════════════════════════════════════════════════════════════════════════
--
-- Por que existe: `docker-compose.dev.yml` levanta `pgvector/pgvector:pg15`,
-- que es Postgres a secas. Las migraciones de `infra/supabase/migrations/`
-- asumen un proyecto Supabase y referencian objetos que ahi no existen:
--
--   · `auth.users`            → FK de `profiles` (0001)
--   · `auth.uid()`            → policies de `profiles` y `constancias`
--   · trigger sobre auth.users→ `on_auth_user_created` (0003)
--   · rol `supabase_auth_admin` → grants del hook de JWT (0003)
--   · roles `anon` / `authenticated` → destinatarios de los revoke/grant
--
-- Sin esto, el primer script del entrypoint falla, y el entrypoint oficial de
-- Postgres aborta la inicializacion: el contenedor nunca llegaba a tener
-- esquema. Es decir, el entorno de desarrollo documentado estaba roto desde
-- el primer `docker compose up`.
--
-- El banco de tests de RLS ya hacia este mismo shim en
-- `services/hr-engine/tests/security/conftest.py`; esto lo replica para dev
-- de modo que ambos entornos ejerciten el mismo esquema.
--
-- ESTO NO ES PRODUCCION. En Supabase Cloud todos estos objetos ya existen y
-- los gestiona la plataforma.
-- ════════════════════════════════════════════════════════════════════════════

create schema if not exists auth;

create table if not exists auth.users (
    id uuid primary key,
    email text,
    raw_user_meta_data jsonb default '{}'::jsonb,
    raw_app_meta_data jsonb default '{}'::jsonb,
    created_at timestamptz not null default now()
);

-- En Supabase, auth.uid() lee el claim `sub` del JWT de la request.
create or replace function auth.uid() returns uuid as $$
    select nullif(
        current_setting('request.jwt.claims', true)::jsonb ->> 'sub',
        ''
    )::uuid;
$$ language sql stable;

do $$ begin
    create role anon nologin;
exception when duplicate_object then null; end $$;

do $$ begin
    create role authenticated nologin;
exception when duplicate_object then null; end $$;

do $$ begin
    create role service_role nologin bypassrls;
exception when duplicate_object then null; end $$;

do $$ begin
    create role supabase_auth_admin nologin;
exception when duplicate_object then null; end $$;

-- Supabase concede estos privilegios por default; aqui hay que hacerlo a mano
-- para que RLS sea lo unico que separa tenants (igual que en la nube).
grant usage on schema public to anon, authenticated, service_role;

alter default privileges in schema public
    grant select, insert, update, delete on tables to anon, authenticated, service_role;
alter default privileges in schema public
    grant usage, select on sequences to anon, authenticated, service_role;
