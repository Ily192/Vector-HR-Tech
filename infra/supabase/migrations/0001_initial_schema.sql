-- ════════════════════════════════════════════════════════════════════════════
-- Vortex Ops · 0001_initial_schema
-- Fecha: 2026-05-08
-- Multi-tenant root + HR domain core + RLS policies
-- ════════════════════════════════════════════════════════════════════════════

-- ─── Extensions ─────────────────────────────────────────────────────────────
create extension if not exists "uuid-ossp";
create extension if not exists "pgcrypto";
create extension if not exists "vector";
create extension if not exists "btree_gist";

-- ─── Enums ──────────────────────────────────────────────────────────────────
create type role_type as enum (
    'Colaborador',
    'HR',
    'Director',
    'SuperAdmin',
    'cliente'
);

create type vacante_status as enum (
    'draft',
    'open',
    'paused',
    'closed',
    'filled'
);

create type seniority_level as enum (
    'junior',
    'semi-senior',
    'senior',
    'lead',
    'manager',
    'director'
);

create type modality as enum (
    'onsite',
    'hybrid',
    'remote'
);

create type application_status as enum (
    'applied',
    'evaluated',
    'shortlisted',
    'interviewed',
    'offered',
    'hired',
    'rejected',
    'withdrawn'
);

create type candidato_source as enum (
    'career-site',
    'linkedin',
    'bumeran',
    'computrabajo',
    'referral',
    'manual'
);

-- ─── empresas (tenant root) ─────────────────────────────────────────────────
create table empresas (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    slug text not null unique,
    paperclip_company_id uuid,
    openclaw_workspace_id text,
    hr_engine_quota_monthly int not null default 1000,
    sales_engine_quota_monthly int not null default 500,
    color_primario text not null default '#1E1B4B'
        check (color_primario ~ '^#[0-9A-Fa-f]{6}$'),
    normativa_interna text,
    google_webhook_url text,
    blacklist_dominios text[] not null default '{}',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index empresas_slug_idx on empresas(slug);

-- ─── profiles ───────────────────────────────────────────────────────────────
-- 1:1 con auth.users de Supabase. empresa_id custom claim en JWT.
create table profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    empresa_id uuid not null references empresas(id) on delete cascade,
    email text not null,
    full_name text not null,
    role role_type not null default 'Colaborador',
    avatar_url text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index profiles_empresa_id_idx on profiles(empresa_id);
create index profiles_email_idx on profiles(email);

-- ─── vacantes ───────────────────────────────────────────────────────────────
create table vacantes (
    id uuid primary key default gen_random_uuid(),
    empresa_id uuid not null references empresas(id) on delete cascade,
    slug text not null,
    title text not null,
    jd text not null,
    icp_text text,
    icp_embedding vector(1536),
    seniority seniority_level,
    modality modality not null default 'remote',
    location text,
    salary_min numeric(12, 2) check (salary_min >= 0),
    salary_max numeric(12, 2) check (salary_max >= 0),
    currency char(3) not null default 'USD',
    status vacante_status not null default 'draft',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    closed_at timestamptz,

    unique (empresa_id, slug)
);

create index vacantes_empresa_id_idx on vacantes(empresa_id);
create index vacantes_status_idx on vacantes(status);
create index vacantes_icp_embedding_hnsw
    on vacantes using hnsw (icp_embedding vector_cosine_ops);

-- ─── candidatos ─────────────────────────────────────────────────────────────
create table candidatos (
    id uuid primary key default gen_random_uuid(),
    empresa_id uuid not null references empresas(id) on delete cascade,
    full_name text not null,
    email text,
    phone text,
    cv_url text,
    cv_embedding vector(1536),
    linkedin_url text,
    headline text,
    summary text,
    source candidato_source not null default 'manual',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    -- email puede repetirse entre empresas pero no dentro de la misma
    unique (empresa_id, email)
);

create index candidatos_empresa_id_idx on candidatos(empresa_id);
create index candidatos_email_idx on candidatos(email);
create index candidatos_cv_embedding_hnsw
    on candidatos using hnsw (cv_embedding vector_cosine_ops);

-- ─── applications ───────────────────────────────────────────────────────────
create table applications (
    id uuid primary key default gen_random_uuid(),
    empresa_id uuid not null references empresas(id) on delete cascade,
    vacante_id uuid not null references vacantes(id) on delete cascade,
    candidato_id uuid not null references candidatos(id) on delete cascade,
    status application_status not null default 'applied',
    fit_score numeric(3, 1) check (fit_score >= 0 and fit_score <= 10),
    fit_rationale text,
    fit_gaps text[] not null default '{}',
    applied_at timestamptz not null default now(),
    decided_at timestamptz,

    unique (vacante_id, candidato_id)
);

create index applications_empresa_id_idx on applications(empresa_id);
create index applications_vacante_id_idx on applications(vacante_id);
create index applications_candidato_id_idx on applications(candidato_id);
create index applications_status_idx on applications(status);

-- ─── runs (cross — control plane shadow) ────────────────────────────────────
-- Espejo local de runs emitidos por Paperclip; el activity log canónico
-- vive en Paperclip. Esta tabla es para correlación local + cost tracking.
create table runs (
    id uuid primary key default gen_random_uuid(),
    empresa_id uuid not null references empresas(id) on delete cascade,
    agent_skill text not null,
    status text not null default 'pending',
    cost_usd numeric(10, 6) not null default 0,
    cost_cap_usd numeric(10, 6),
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    error_message text,
    payload jsonb
);

create index runs_empresa_id_idx on runs(empresa_id);
create index runs_status_idx on runs(status);
create index runs_started_at_idx on runs(started_at desc);

-- ─── activity_log (append-only, hash chain) ─────────────────────────────────
create table activity_log (
    id bigserial primary key,
    empresa_id uuid not null,
    actor_id uuid,
    actor_role role_type,
    action text not null,
    resource_type text,
    resource_id uuid,
    payload jsonb not null default '{}'::jsonb,
    prev_hash text,
    hash text not null,
    ts timestamptz not null default now()
);

create index activity_log_empresa_id_ts_idx on activity_log(empresa_id, ts desc);
create index activity_log_resource_idx on activity_log(resource_type, resource_id);

-- Inmutabilidad: bloquear UPDATE/DELETE
create or replace function activity_log_immutable() returns trigger as $$
begin
    raise exception 'activity_log is append-only; UPDATE/DELETE forbidden';
end;
$$ language plpgsql;

create trigger activity_log_no_update
    before update on activity_log
    for each row execute function activity_log_immutable();

create trigger activity_log_no_delete
    before delete on activity_log
    for each row execute function activity_log_immutable();

-- ─── updated_at trigger ─────────────────────────────────────────────────────
create or replace function set_updated_at() returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

create trigger empresas_updated_at before update on empresas
    for each row execute function set_updated_at();
create trigger profiles_updated_at before update on profiles
    for each row execute function set_updated_at();
create trigger vacantes_updated_at before update on vacantes
    for each row execute function set_updated_at();
create trigger candidatos_updated_at before update on candidatos
    for each row execute function set_updated_at();

-- ════════════════════════════════════════════════════════════════════════════
-- Row-Level Security (RLS) — defensa multi-tenant
-- ════════════════════════════════════════════════════════════════════════════

-- Helper: extrae empresa_id del JWT claim
create or replace function auth.empresa_id() returns uuid as $$
    select coalesce(
        nullif(current_setting('request.jwt.claim.empresa_id', true), ''),
        nullif(current_setting('request.jwt.claims', true)::jsonb ->> 'empresa_id', '')
    )::uuid;
$$ language sql stable;

-- Helper: rol del JWT claim
create or replace function auth.role() returns text as $$
    select coalesce(
        nullif(current_setting('request.jwt.claim.role', true), ''),
        nullif(current_setting('request.jwt.claims', true)::jsonb ->> 'role', '')
    );
$$ language sql stable;

-- ─── RLS: empresas ──────────────────────────────────────────────────────────
alter table empresas enable row level security;

create policy empresas_self_read on empresas
    for select using (id = auth.empresa_id());

create policy empresas_superadmin_all on empresas
    for all using (auth.role() = 'SuperAdmin');

-- ─── RLS: profiles ──────────────────────────────────────────────────────────
alter table profiles enable row level security;

create policy profiles_tenant_read on profiles
    for select using (empresa_id = auth.empresa_id());

create policy profiles_self_update on profiles
    for update using (id = auth.uid());

create policy profiles_hr_manage on profiles
    for all using (
        empresa_id = auth.empresa_id()
        and auth.role() in ('HR', 'Director', 'SuperAdmin')
    );

-- ─── RLS: vacantes ──────────────────────────────────────────────────────────
alter table vacantes enable row level security;

-- Lectura pública SOLO de vacantes 'open' (career-site)
create policy vacantes_public_open_read on vacantes
    for select using (status = 'open');

create policy vacantes_tenant_all on vacantes
    for all using (
        empresa_id = auth.empresa_id()
        and auth.role() in ('HR', 'Director', 'SuperAdmin')
    );

-- ─── RLS: candidatos ────────────────────────────────────────────────────────
alter table candidatos enable row level security;

create policy candidatos_tenant_isolation on candidatos
    for all using (empresa_id = auth.empresa_id());

-- ─── RLS: applications ──────────────────────────────────────────────────────
alter table applications enable row level security;

create policy applications_tenant_isolation on applications
    for all using (empresa_id = auth.empresa_id());

-- ─── RLS: runs ──────────────────────────────────────────────────────────────
alter table runs enable row level security;

create policy runs_tenant_isolation on runs
    for select using (empresa_id = auth.empresa_id());

-- ─── RLS: activity_log ──────────────────────────────────────────────────────
alter table activity_log enable row level security;

create policy activity_log_tenant_read on activity_log
    for select using (empresa_id = auth.empresa_id());

-- service_role bypass automático en Supabase para activity log inserts.

-- ════════════════════════════════════════════════════════════════════════════
-- Seed mínimo (solo dev) — eliminar antes de prod
-- ════════════════════════════════════════════════════════════════════════════
-- insert into empresas (name, slug, color_primario) values
--     ('Vector HR Tech', 'vector-hr', '#1E1B4B'),
--     ('Siete', 'siete', '#FF7F00');
