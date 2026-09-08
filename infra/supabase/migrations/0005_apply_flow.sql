-- ════════════════════════════════════════════════════════════════════════════
-- Vortex Ops · 0005_apply_flow
-- Fecha: 2026-09-07
-- Storage de CVs + via de escritura publica para "candidato aplica".
-- Requiere: 0001..0004
-- ════════════════════════════════════════════════════════════════════════════
--
-- Por que hace falta: el flujo core del Cycle 1 es "subir CV en career-site →
-- ver score en hrbp". Hoy es imposible por dos razones:
--
--   1. No existe ningun bucket de Storage ni policies para el. `candidatos.cv_url`
--      es un `text` libre que nadie escribe.
--   2. `anon` no tiene ninguna policy de INSERT en `candidatos` ni en
--      `applications`. Con `public.empresa_id()` nulo, `empresa_id =
--      public.empresa_id()` evalua a NULL → falso → denegado.
--
-- Decision de diseño: el candidato NO escribe directo en la base ni en Storage.
--
--   · El fichero lo sube el servidor (Server Action del career-site) con la
--     service_role key. Dar INSERT sobre `storage.objects` a `anon` convertiria
--     el bucket en un dropbox publico.
--   · La fila la crea `public.aplicar_a_vacante()`, una funcion
--     `security definer` de superficie minima: recibe los datos del formulario
--     y no deja elegir empresa_id, status ni fit_score.
--
-- Lo que esta funcion NO puede hacer, y hay que resolver en la capa de app:
-- rate limiting y anti-bot. Una RPC ejecutable por `anon` que inserta filas es
-- un vector de spam; debe ir detras del rate limiter del engine o de un
-- verificador de captcha en la Server Action.
-- ════════════════════════════════════════════════════════════════════════════

begin;

-- ─── Bucket de CVs ──────────────────────────────────────────────────────────
--
-- El schema `storage` solo existe en Supabase. El docker-compose de desarrollo
-- levanta un Postgres plano, y el bench de RLS tambien: sin esta guarda, la
-- migracion abortaria ahi y romperia el entorno local entero.
do $$
begin
    if to_regclass('storage.buckets') is null then
        raise notice
            'schema storage ausente (Postgres plano): se omite el bucket cvs. '
            'En Supabase esta parte si se aplica.';
        return;
    end if;

    insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
    values (
        'cvs', 'cvs', false, 10485760,
        array['application/pdf',
              'application/msword',
              'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
    )
    on conflict (id) do nothing;

    -- Convencion de path: {empresa_id}/{candidato_id}/{archivo}
    -- El primer segmento es el tenant, asi que RLS puede filtrar por el.
    execute $pol$
        drop policy if exists cvs_tenant_read on storage.objects;
        create policy cvs_tenant_read on storage.objects
            for select
            using (
                bucket_id = 'cvs'
                and (storage.foldername(name))[1] = (select public.empresa_id())::text
                and (select public.app_role()) in ('HR', 'Director')
            );
    $pol$;

    -- Deliberadamente NO hay policy de INSERT/UPDATE/DELETE: ni `anon` ni
    -- `authenticated` escriben en el bucket. La subida la hace la Server Action
    -- con service_role, que valida tipo y tamaño antes de escribir.
end $$;

-- ─── aplicar_a_vacante ──────────────────────────────────────────────────────
--
-- Unica via por la que un candidato entra al pipeline. Devuelve el id de la
-- application creada (o la existente, si ya habia aplicado a esa vacante).
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
    v_email        text := lower(trim(p_email));
    v_name         text := trim(p_full_name);
begin
    -- Solo vacantes abiertas. Si esta en draft o cerrada, no existe para el
    -- mundo exterior y el mensaje no debe revelar la diferencia.
    select empresa_id into v_empresa
      from public.vacantes
     where id = p_vacante_id and status = 'open';

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

    -- El CV tiene que vivir bajo el tenant de la vacante. Sin este check, un
    -- path arbitrario dejaria apuntar `cv_url` a un fichero de otra empresa.
    if p_cv_path is not null
       and p_cv_path not like v_empresa::text || '/%' then
        raise exception using
            errcode = '22023',
            message = 'la ruta del CV no corresponde a la empresa de la vacante';
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

commit;
