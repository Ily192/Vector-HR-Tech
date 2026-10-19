-- ════════════════════════════════════════════════════════════════════════════
-- Vortex Ops · 0011_app_role_en_storage
-- Fecha: 2026-10-20
-- `public.app_role()` lee primero el rol de aplicación del JWT (`app_metadata`).
-- Requiere: 0001..0010
-- ════════════════════════════════════════════════════════════════════════════
--
-- 0001 leía primero el GUC `request.jwt.claim.role`. PostgREST ya no lo define,
-- pero la Storage API de Supabase sí, y le pone el rol de Postgres del JWT
-- (`authenticated`). Dentro de Storage, `app_role()` valía 'authenticated': la
-- policy `cvs_tenant_read` (0005) nunca se cumplía, y la empresa no podía bajar
-- ni firmar las URLs de sus propios CVs, que es la descarga del .zip del plan
-- gratis (ADR-017 y ADR-019).
--
-- El banco de pruebas no tiene Storage, así que no se veía. Lo encontró el humo
-- contra el Supabase local de la CLI (`pnpm db:start`), con las imágenes reales.
--
-- Ahora gana `app_metadata.app_role`, que pone el hook del JWT y el usuario no
-- puede editar. El GUC queda de respaldo solo si trae un rol de la aplicación:
-- es lo que hace el hr-engine (`set_tenant_context`), que no tiene JWT.
-- ════════════════════════════════════════════════════════════════════════════

begin;

create or replace function public.app_role() returns text
    language sql
    stable
    security invoker
    set search_path = ''
as $$
    select coalesce(
        nullif(pg_catalog.current_setting('request.jwt.claims', true), '')::jsonb
               -> 'app_metadata' ->> 'app_role',
        case
            when pg_catalog.current_setting('request.jwt.claim.role', true)
                 = any (pg_catalog.enum_range(null::public.role_type)::text[])
            then pg_catalog.current_setting('request.jwt.claim.role', true)
        end
    );
$$;

commit;
