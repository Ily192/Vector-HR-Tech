-- ════════════════════════════════════════════════════════════════════════════
-- Vortex Ops · 0002_hr_phase2
-- Fecha: 2026-05-12
-- HR domain — evaluación conductual, entrevistas y constancias.
-- Requiere: 0001_initial_schema.sql
-- ════════════════════════════════════════════════════════════════════════════

-- ─── Enums ──────────────────────────────────────────────────────────────────
create type psicometrico_status as enum (
    'pending',
    'in_progress',
    'completed',
    'expired',
    'invalidated'
);

create type entrevista_modality as enum (
    'video',
    'phone',
    'onsite'
);

create type entrevista_status as enum (
    'scheduled',
    'rescheduled',
    'completed',
    'no_show',
    'cancelled'
);

create type constancia_type as enum (
    'laboral',
    'laboral_con_salario',
    'no_adeudo',
    'antiguedad',
    'ingresos',
    'no_inhabilitacion'
);

create type constancia_status as enum (
    'requested',
    'generated',
    'signed',
    'delivered',
    'revoked'
);

-- ─── psicometricos ──────────────────────────────────────────────────────────
-- Resultado del test psicométrico. Link único por token (Test-psicometricos-main
-- vive como ruta en apps/candidate y postea aquí).
create table psicometricos (
    id uuid primary key default gen_random_uuid(),
    empresa_id uuid not null references empresas(id) on delete cascade,
    application_id uuid not null references applications(id) on delete cascade,
    token text not null unique,
    status psicometrico_status not null default 'pending',
    -- Big Five normalizado 0-100 (output del informe).
    big5_openness numeric(5, 2) check (big5_openness between 0 and 100),
    big5_conscientiousness numeric(5, 2) check (big5_conscientiousness between 0 and 100),
    big5_extraversion numeric(5, 2) check (big5_extraversion between 0 and 100),
    big5_agreeableness numeric(5, 2) check (big5_agreeableness between 0 and 100),
    big5_neuroticism numeric(5, 2) check (big5_neuroticism between 0 and 100),
    raw_answers jsonb,
    report_summary text,
    report_pdf_url text,
    started_at timestamptz,
    completed_at timestamptz,
    expires_at timestamptz not null default (now() + interval '7 days'),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index psicometricos_empresa_id_idx on psicometricos(empresa_id);
create index psicometricos_application_id_idx on psicometricos(application_id);
create index psicometricos_token_idx on psicometricos(token);
create index psicometricos_status_idx on psicometricos(status);

-- Solo un test activo (pending/in_progress) por application.
create unique index psicometricos_one_active_per_application
    on psicometricos(application_id)
    where status in ('pending', 'in_progress');

create trigger psicometricos_updated_at before update on psicometricos
    for each row execute function set_updated_at();

-- ─── entrevistas ────────────────────────────────────────────────────────────
create table entrevistas (
    id uuid primary key default gen_random_uuid(),
    empresa_id uuid not null references empresas(id) on delete cascade,
    application_id uuid not null references applications(id) on delete cascade,
    interviewer_id uuid references profiles(id) on delete set null,
    modality entrevista_modality not null default 'video',
    status entrevista_status not null default 'scheduled',
    slot tstzrange not null,
    location text,
    meeting_url text,
    calendar_event_id text,
    transcript text,
    score numeric(3, 1) check (score between 0 and 10),
    notes text,
    decided_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    -- Evita doble-agendado del mismo interviewer en slots solapados.
    exclude using gist (
        interviewer_id with =,
        slot with &&
    ) where (status in ('scheduled', 'rescheduled'))
);

create index entrevistas_empresa_id_idx on entrevistas(empresa_id);
create index entrevistas_application_id_idx on entrevistas(application_id);
create index entrevistas_interviewer_id_idx on entrevistas(interviewer_id);
create index entrevistas_slot_gist on entrevistas using gist (slot);
create index entrevistas_status_idx on entrevistas(status);

create trigger entrevistas_updated_at before update on entrevistas
    for each row execute function set_updated_at();

-- ─── constancias ────────────────────────────────────────────────────────────
-- Documentos firmados generados al colaborador (post-hire o on-demand).
create table constancias (
    id uuid primary key default gen_random_uuid(),
    empresa_id uuid not null references empresas(id) on delete cascade,
    profile_id uuid not null references profiles(id) on delete cascade,
    type constancia_type not null,
    status constancia_status not null default 'requested',
    pdf_url text,
    signed_pdf_url text,
    signature_hash text,
    issued_by uuid references profiles(id) on delete set null,
    issued_at timestamptz,
    delivered_at timestamptz,
    revoked_at timestamptz,
    revoke_reason text,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index constancias_empresa_id_idx on constancias(empresa_id);
create index constancias_profile_id_idx on constancias(profile_id);
create index constancias_status_idx on constancias(status);
create index constancias_type_idx on constancias(type);

create trigger constancias_updated_at before update on constancias
    for each row execute function set_updated_at();

-- ════════════════════════════════════════════════════════════════════════════
-- RLS — tenant isolation
-- ════════════════════════════════════════════════════════════════════════════

alter table psicometricos enable row level security;

-- Lectura pública por token (candidato accede sin auth para responder el test).
create policy psicometricos_public_token_read on psicometricos
    for select using (
        status in ('pending', 'in_progress')
        and expires_at > now()
    );

-- Update por token (candidato envía respuestas) — limitado a status válidos.
create policy psicometricos_public_token_update on psicometricos
    for update using (
        status in ('pending', 'in_progress')
        and expires_at > now()
    )
    with check (
        status in ('in_progress', 'completed')
    );

-- HR del tenant tiene control total.
create policy psicometricos_tenant_manage on psicometricos
    for all using (
        empresa_id = auth.empresa_id()
        and auth.role() in ('HR', 'Director', 'SuperAdmin')
    );

alter table entrevistas enable row level security;

create policy entrevistas_tenant_isolation on entrevistas
    for all using (empresa_id = auth.empresa_id());

alter table constancias enable row level security;

-- Colaborador ve sus propias constancias; HR ve todas del tenant.
create policy constancias_self_read on constancias
    for select using (profile_id = auth.uid());

create policy constancias_tenant_manage on constancias
    for all using (
        empresa_id = auth.empresa_id()
        and auth.role() in ('HR', 'Director', 'SuperAdmin')
    );

-- ════════════════════════════════════════════════════════════════════════════
-- Trigger: auto-sync empresa_id desde application al insertar dependientes.
-- Why: evita que app code introduzca tenant drift entre application y sus hijos.
-- ════════════════════════════════════════════════════════════════════════════
create or replace function enforce_empresa_id_from_application() returns trigger as $$
declare
    parent_empresa uuid;
begin
    select empresa_id into parent_empresa from applications where id = new.application_id;
    if parent_empresa is null then
        raise exception 'application % not found', new.application_id;
    end if;
    if new.empresa_id is null then
        new.empresa_id := parent_empresa;
    elsif new.empresa_id <> parent_empresa then
        raise exception 'tenant drift: empresa_id % does not match application.empresa_id %',
            new.empresa_id, parent_empresa;
    end if;
    return new;
end;
$$ language plpgsql;

create trigger psicometricos_enforce_empresa
    before insert on psicometricos
    for each row execute function enforce_empresa_id_from_application();

create trigger entrevistas_enforce_empresa
    before insert on entrevistas
    for each row execute function enforce_empresa_id_from_application();
