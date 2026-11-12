-- ════════════════════════════════════════════════════════════════════════════
-- Vortex Ops · 0017_rol_del_career_site
-- Fecha: 2026-11-11
-- El career site deja la service_role: el rol `career_site`, con su propio JWT.
-- Requiere: 0001..0016
-- ════════════════════════════════════════════════════════════════════════════
--
-- Por qué: el career site pasa a Vercel (tercera enmienda de ADR-020). Hasta hoy
-- subía el CV con la service_role, que ignora RLS y ve a todos los tenants: en
-- Vercel esa clave quedaría guardada fuera del servidor. Con este rol, si la clave
-- se filtra, lo peor que se puede hacer es subir archivos al bucket `cvs`, con el
-- tamaño y los tipos del bucket, a la carpeta de una empresa con vacantes abiertas.
--
-- Lo que hace el career site y lo que este rol le deja:
--   1. Leer el `id` y el `empresa_id` de la vacante abierta por su slug, porque la
--      ruta del CV empieza por la empresa → SELECT de (id, empresa_id, slug,
--      status) en `vacantes`, solo de las filas `open`.
--   2. Subir el CV → INSERT en `storage.objects`, solo en `cvs`, con la forma
--      `{empresa}/{uuid}.pdf|docx` y en la carpeta de una empresa con alguna
--      vacante abierta.
--   3. Borrar ese CV si `aplicar_a_vacante` falla → DELETE en `cvs`, solo de
--      objetos de menos de 15 minutos y solo si la petición trae su ruta exacta en
--      la cabecera `x-cv-ruta`.
--   La aplicación sigue entrando por `aplicar_a_vacante` con la clave anon (0005).
--
-- Por qué el borrado pide la ruta en una cabecera: el DELETE de la Storage API
-- (v1.79.36, src/storage/database/pg.ts, deleteObjects) filtra por `name` y hace
-- `RETURNING *`. En Postgres, leer columnas en el WHERE o el RETURNING exige que la
-- fila pase también una policy de SELECT (CREATE POLICY, "Policies Applied by
-- Command Type"). Una policy de SELECT abierta dejaría listar y bajar los CVs de
-- los últimos 15 minutos. Atada a la cabecera, solo ve la fila quien ya conoce su
-- ruta, que lleva un uuid aleatorio: listar devuelve vacío y bajar un CV ajeno es
-- adivinar un uuid. La Storage API copia las cabeceras de la petición al GUC
-- `request.headers` (src/internal/database/postgres/scope.ts).
--
-- Cómo entra el rol:
--   · PostgREST y la Storage API hacen `set role` al claim `role` del JWT
--     (Storage: `set_config('role', …)` con `payload.role`). PostgREST se conecta
--     como `authenticator`, y la Storage API como `supabase_storage_admin`, que en
--     la imagen de Supabase es miembro de `authenticator` (supabase/postgres,
--     20231013070755_grant_authenticator_to_supabase_storage_admin.sql). Basta con
--     `grant career_site to authenticator`.
--   · El gateway (Envoy) solo acepta como `apikey` la anon o la service_role: el
--     career site manda la anon en `apikey` y este JWT en `Authorization`.
--
-- En el banco de pruebas (Postgres plano) no hay `storage` ni `authenticator`: esas
-- partes se omiten con un aviso, como en 0005.
-- ════════════════════════════════════════════════════════════════════════════

begin;

do $$
begin
    create role career_site nologin noinherit;
exception when duplicate_object then null;
end $$;

comment on role career_site is
    'El career site en Vercel: lee la vacante abierta y sube el CV a cvs (0017). Su JWT lo firma generar_secretos.py.';

-- ─── 1. Vacantes: las columnas que usa, solo de las abiertas ────────────────
revoke all on public.vacantes from career_site;
grant usage on schema public to career_site;
grant select (id, empresa_id, slug, status) on public.vacantes to career_site;

drop policy if exists vacantes_career_site_abiertas on public.vacantes;
create policy vacantes_career_site_abiertas on public.vacantes
    for select to career_site
    using (status = 'open');

-- ─── 2 y 3. El bucket de CVs ────────────────────────────────────────────────
do $$
begin
    if exists (select 1 from pg_catalog.pg_roles where rolname = 'authenticator') then
        grant career_site to authenticator;
    else
        raise notice 'sin el rol authenticator (Postgres plano): career_site no entra por PostgREST ni Storage.';
    end if;

    if to_regclass('storage.objects') is null then
        raise notice 'schema storage ausente (Postgres plano): se omiten las policies de cvs para career_site.';
        return;
    end if;

    grant usage on schema storage to career_site;
    -- SELECT a nivel de tabla para el WHERE y el RETURNING del borrado; las filas las
    -- filtra la policy de abajo.
    grant select, insert, delete on storage.objects to career_site;

    execute $pol$
        drop policy if exists cvs_career_site_subir on storage.objects;
        create policy cvs_career_site_subir on storage.objects
            for insert to career_site
            with check (
                bucket_id = 'cvs'
                and name ~ '^[0-9a-f-]{36}/[0-9a-f-]{36}\.(pdf|docx)$'
                and exists (
                    select 1
                      from public.vacantes v
                     where v.status = 'open'
                       and v.empresa_id::text = pg_catalog.split_part(name, '/', 1)
                )
            );

        drop policy if exists cvs_career_site_ver_para_borrar on storage.objects;
        create policy cvs_career_site_ver_para_borrar on storage.objects
            for select to career_site
            using (
                bucket_id = 'cvs'
                and created_at > pg_catalog.now() - interval '15 minutes'
                and name = nullif(pg_catalog.current_setting('request.headers', true), '')::json
                           ->> 'x-cv-ruta'
            );

        drop policy if exists cvs_career_site_borrar on storage.objects;
        create policy cvs_career_site_borrar on storage.objects
            for delete to career_site
            using (
                bucket_id = 'cvs'
                and created_at > pg_catalog.now() - interval '15 minutes'
                and name = nullif(pg_catalog.current_setting('request.headers', true), '')::json
                           ->> 'x-cv-ruta'
            );
    $pol$;
end $$;

commit;
