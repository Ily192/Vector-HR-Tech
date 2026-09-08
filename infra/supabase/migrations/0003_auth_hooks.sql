-- ════════════════════════════════════════════════════════════════════════════
-- Vortex Ops · 0003_auth_hooks
-- Fecha: 2026-05-12 · Revisada 2026-09-07 (hardening de seguridad)
-- Triggers + JWT custom claims hook para Supabase Auth.
-- Requiere: 0001_initial_schema.sql, 0002_hr_phase2.sql
-- ════════════════════════════════════════════════════════════════════════════
--
-- HISTORIA — por que esta migracion se reescribio antes de aplicarse nunca:
--
-- La version original derivaba `empresa_id` y `role` de `raw_user_meta_data`.
-- Ese campo es literalmente el `options.data` de `supabase.auth.signUp()`:
-- lo controla el cliente al 100% y GoTrue no lo valida. Como el trigger corre
-- `security definer` (bypassa RLS), cualquiera con la anon key —que es publica
-- por diseño— podia hacer:
--
--   supabase.auth.signUp({ email, password, options: { data: {
--       empresa_id: '<uuid de la victima>', role: 'SuperAdmin' } } })
--
-- y quedar como SuperAdmin dentro del tenant elegido. El uuid de la victima ni
-- siquiera habia que adivinarlo: `vacantes` lo expone a `anon`.
--
-- Regla que aplica esta version: del metadata de signup NO se confia en nada
-- salvo `full_name`. El vinculo usuario→empresa se establece SOLO por una
-- invitacion emitida por alguien que ya pertenece al tenant.
-- ════════════════════════════════════════════════════════════════════════════

-- ─── invitations ────────────────────────────────────────────────────────────
-- Unica fuente de verdad para "este email puede unirse a esta empresa con este
-- rol". La escribe HR/Director desde el cockpit; el signup solo la consume.
create table if not exists public.invitations (
    id uuid primary key default gen_random_uuid(),
    empresa_id uuid not null references public.empresas(id) on delete cascade,
    -- Normalizado a minusculas por el check; el esquema usa text en todas
    -- las columnas de email y citext no esta habilitada en 0001.
    email text not null check (email = lower(email)),
    role role_type not null default 'Colaborador',
    -- Solo el hash. El token en claro se envia por email y no se persiste.
    token_hash text not null unique,
    invited_by uuid references public.profiles(id) on delete set null,
    expires_at timestamptz not null default (now() + interval '7 days'),
    consumed_at timestamptz,
    consumed_by uuid references auth.users(id) on delete set null,
    created_at timestamptz not null default now()
);

create index if not exists invitations_empresa_id_idx on public.invitations(empresa_id);
create index if not exists invitations_email_idx on public.invitations(email);

-- Una invitacion viva por (empresa, email).
create unique index if not exists invitations_one_active_per_email
    on public.invitations(empresa_id, email)
    where consumed_at is null;

alter table public.invitations enable row level security;
-- Sin FORCE a proposito: `handle_new_user()` es `security definer` y lee y
-- actualiza esta tabla durante el signup, cuando todavia no hay claims de
-- tenant. Con FORCE, la policy de abajo denegaria y el alta fallaria siempre.
-- Ver la nota extensa en 0004 §9.

-- HR/Director gestionan invitaciones de SU empresa, y NO pueden repartir
-- SuperAdmin (que es un privilegio de plataforma, no de tenant — ver 0004).
drop policy if exists invitations_tenant_manage on public.invitations;
create policy invitations_tenant_manage on public.invitations
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

-- `anon` no tiene nada que hacer aqui: el token se valida dentro del trigger,
-- que corre con privilegios elevados.
revoke all on public.invitations from anon;

-- ─── handle_new_user ────────────────────────────────────────────────────────
-- Al crear un auth.users, poblamos profiles. `empresa_id` y `role` salen
-- EXCLUSIVAMENTE de una invitacion valida, nunca del metadata del signup.
create or replace function public.handle_new_user() returns trigger
    language plpgsql
    security definer
    -- search_path vacio: con `public` en el path y CREATE concedido sobre el
    -- schema, un atacante podria shadowear los objetos que esta funcion
    -- resuelve y ejecutarlos como definer.
    set search_path = ''
as $$
declare
    invite_token text;
    inv          public.invitations%rowtype;
    target_name  text;
begin
    target_name := coalesce(
        nullif(new.raw_user_meta_data ->> 'full_name', ''),
        split_part(new.email, '@', 1)
    );

    invite_token := nullif(new.raw_user_meta_data ->> 'invite_token', '');

    if invite_token is null then
        raise exception using
            errcode = '22023',
            message = 'signup requiere invite_token',
            hint    = 'Pide a HR de tu empresa que te envie una invitacion.';
    end if;

    select * into inv
      from public.invitations
     where token_hash = encode(sha256(invite_token::bytea), 'hex')
       and consumed_at is null
       and expires_at > now()
     for update;

    if not found then
        raise exception using
            errcode = '22023',
            message = 'invitacion invalida, ya usada o expirada';
    end if;

    -- El email del signup debe ser el invitado. Sin esto, un token filtrado
    -- deja entrar a cualquiera.
    if inv.email <> lower(new.email) then
        raise exception using
            errcode = '22023',
            message = 'la invitacion no corresponde a este email';
    end if;

    insert into public.profiles (id, empresa_id, email, full_name, role)
    values (new.id, inv.empresa_id, new.email, target_name, inv.role);

    update public.invitations
       set consumed_at = now(),
           consumed_by = new.id
     where id = inv.id;

    return new;
end;
$$;

-- Solo el trigger la invoca.
revoke execute on function public.handle_new_user() from public, anon, authenticated;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- ─── custom_access_token_hook ──────────────────────────────────────────────
-- Inyecta empresa_id y app_role en el JWT para que public.empresa_id() y
-- public.app_role() funcionen sin un round-trip extra a la DB.
-- Supabase Auth llama esta funcion con { user_id, claims } y espera el claims
-- actualizado de vuelta.
--
-- Los claims van bajo `app_metadata`, NUNCA en la raiz:
--   · `role` en la raiz es reservado — PostgREST hace `SET LOCAL ROLE` con el.
--     Escribir 'HR' ahi rompia toda peticion autenticada con 42704.
--   · `user_metadata` lo puede editar el propio usuario con updateUser().
--     `app_metadata` no.
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
begin
    select empresa_id, role::text
        into profile_empresa, profile_role
        from public.profiles
        where id = user_id;

    if profile_empresa is not null then
        app_meta := jsonb_set(app_meta, '{empresa_id}',
                              to_jsonb(profile_empresa::text));
    end if;
    if profile_role is not null then
        app_meta := jsonb_set(app_meta, '{app_role}', to_jsonb(profile_role));
    end if;

    claims := jsonb_set(claims, '{app_metadata}', app_meta);
    return jsonb_set(event, '{claims}', claims);
end;
$$;

-- Permisos necesarios para que Supabase Auth pueda invocar el hook.
grant usage on schema public to supabase_auth_admin;
grant execute on function public.custom_access_token_hook(jsonb) to supabase_auth_admin;
grant select on public.profiles to supabase_auth_admin;
revoke execute on function public.custom_access_token_hook(jsonb) from authenticated, anon, public;

-- Nota: la simulacion de claims JWT en tests se hace directamente con
-- `set_config('request.jwt.claims', ..., false)` en la conftest. Mantener
-- helpers de testing fuera del schema productivo evita el riesgo de que un
-- usuario `authenticated` los invoque para impersonar otro tenant.
