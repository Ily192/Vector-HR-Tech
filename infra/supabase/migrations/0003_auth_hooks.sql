-- ════════════════════════════════════════════════════════════════════════════
-- Vortex Ops · 0003_auth_hooks
-- Fecha: 2026-05-12
-- Triggers + JWT custom claims hook para Supabase Auth.
-- Requiere: 0001_initial_schema.sql, 0002_hr_phase2.sql
-- ════════════════════════════════════════════════════════════════════════════

-- ─── handle_new_user ────────────────────────────────────────────────────────
-- Al crear un auth.users, poblamos profiles con empresa_id/role derivados
-- de los user_metadata (front-end los setea en signup) o caemos al default.
create or replace function public.handle_new_user() returns trigger
    language plpgsql
    security definer
    set search_path = public, auth
as $$
declare
    target_empresa uuid;
    target_role role_type;
    target_name text;
begin
    target_empresa := nullif(new.raw_user_meta_data ->> 'empresa_id', '')::uuid;
    target_role := coalesce(
        nullif(new.raw_user_meta_data ->> 'role', '')::role_type,
        'Colaborador'::role_type
    );
    target_name := coalesce(
        new.raw_user_meta_data ->> 'full_name',
        split_part(new.email, '@', 1)
    );

    -- Si no se especificó empresa, no creamos profile — flujo de invitación
    -- requerirá un paso explícito en /onboarding.
    if target_empresa is null then
        return new;
    end if;

    insert into public.profiles (id, empresa_id, email, full_name, role)
    values (new.id, target_empresa, new.email, target_name, target_role);

    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- ─── custom_access_token_hook ──────────────────────────────────────────────
-- Inyecta empresa_id y role en el JWT (claims) para que auth.empresa_id() y
-- auth.role() funcionen sin un round-trip extra a la DB.
-- Supabase Auth llama esta función con { user_id, claims } y espera claims actualizado.
create or replace function public.custom_access_token_hook(event jsonb)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = public
as $$
declare
    user_id uuid := (event -> 'user_id')::uuid;
    claims jsonb := event -> 'claims';
    profile_empresa uuid;
    profile_role text;
begin
    select empresa_id, role::text
        into profile_empresa, profile_role
        from public.profiles
        where id = user_id;

    if profile_empresa is not null then
        claims := jsonb_set(claims, '{empresa_id}', to_jsonb(profile_empresa::text));
    end if;
    if profile_role is not null then
        claims := jsonb_set(claims, '{role}', to_jsonb(profile_role));
    end if;

    return jsonb_set(event, '{claims}', claims);
end;
$$;

-- Permisos necesarios para que Supabase Auth pueda invocar el hook.
grant usage on schema public to supabase_auth_admin;
grant execute on function public.custom_access_token_hook(jsonb) to supabase_auth_admin;
revoke execute on function public.custom_access_token_hook(jsonb) from authenticated, anon, public;

-- Nota: la simulación de claims JWT en tests se hace directamente con
-- `set_config('request.jwt.claims', ..., false)` en la conftest. Mantener
-- helpers de testing fuera del schema productivo evita el riesgo de que un
-- usuario `authenticated` los invoque para impersonar otro tenant.
