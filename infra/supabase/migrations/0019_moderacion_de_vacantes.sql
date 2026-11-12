-- ════════════════════════════════════════════════════════════════════════════
-- Vortex Ops · 0019_moderacion_de_vacantes
-- Fecha: 2026-11-12
-- Verificación de empresas y moderación de vacantes antes del career site (ADR-022).
-- Requiere: 0001..0017 (y 0018 si existe; no depende de ella)
-- ════════════════════════════════════════════════════════════════════════════
--
-- Por qué: el alta en el plan gratis deja de ser manual (enmienda de ADR-017), así
-- que cualquiera puede abrir una cuenta y publicar. Una vacante falsa (cobra un
-- curso, pide datos bancarios, manda a un WhatsApp) le hace daño a un candidato
-- real y a la marca. Desde aquí una vacante del panel no sale al career site hasta
-- que el hr-engine la modera (`moderacion = 'publicada'`).
--
--   1. `empresas`: cómo publica (`publica_para`), su web y su LinkedIn, y la insignia
--      `verificada`. Las escribe el hr-engine con el rol dueño: el tenant no tiene
--      policy de UPDATE en `empresas` (0001), así que no puede darse la insignia.
--   2. `vacantes.moderacion` y sus motivos. El panel no las puede escribir: las
--      fija un trigger. Al crearla queda 'pendiente'; si se edita lo que el
--      candidato ve, vuelve a 'pendiente'.
--   3. `vacantes_publicas`, `aplicar_a_vacante` y el rol `career_site` (0017) solo
--      ven las 'publicada'. La vista suma la insignia y, para reclutadores
--      independientes, quién publica.
--   4. Una vacante rechazada no cuenta en el tope de activas ni en las
--      publicaciones de 30 días (0010): la empresa no pierde una publicación por
--      un falso positivo.
--   5. `reportar_vacante()`: el botón "Reportar vacante" del career site. Solo la
--      llama el rol `career_site`; la IP se guarda como hash con sal. Con dos
--      reportes de IPs distintas la vacante se oculta y pasa a revisión.
--
-- Las filas que ya existen quedan 'publicada' (el default de la columna). Lo que
-- inserta el rol dueño (Vector HR, el seed, la CLI) también: la moderación es para
-- lo que llega del panel, con sesión de tenant.
-- ════════════════════════════════════════════════════════════════════════════

begin;

-- ─── 1. Empresas: cómo publican y la insignia ───────────────────────────────

alter table public.empresas
    add column if not exists publica_para text not null default 'propia',
    add column if not exists web text,
    add column if not exists linkedin text,
    add column if not exists verificada boolean not null default false,
    add column if not exists verificada_en timestamptz;

do $$
begin
    alter table public.empresas
        add constraint empresas_publica_para_valida
            check (publica_para in ('propia', 'clientes'));
exception when duplicate_object then null;
end $$;

do $$
begin
    alter table public.empresas
        add constraint empresas_web_https
            check (web is null or (web ~ '^https://[^[:space:]]+$' and char_length(web) <= 300));
exception when duplicate_object then null;
end $$;

do $$
begin
    alter table public.empresas
        add constraint empresas_linkedin_https
            check (linkedin is null
                   or (linkedin ~ '^https://([a-z0-9-]+\.)?linkedin\.com/[^[:space:]]+$'
                       and char_length(linkedin) <= 300));
exception when duplicate_object then null;
end $$;

comment on column public.empresas.publica_para is
    '''propia'': publica para su empresa. ''clientes'': reclutador independiente o agencia; sus vacantes siempre pasan por revisión (ADR-022).';
comment on column public.empresas.verificada is
    'Insignia "Empresa verificada": el dominio del correo confirmado coincide con el de su web, o Vector HR la revisó a mano. La pone el hr-engine (ADR-022).';

-- ─── 2. Vacantes: el estado de moderación ───────────────────────────────────

do $$
begin
    create type public.moderacion_vacante as enum (
        'pendiente',    -- recién creada o editada: la modera el siguiente barrido
        'publicada',    -- visible en el career site
        'en_revision',  -- la revisa una persona de Vector HR
        'rechazada',    -- riesgo alto o rechazada en la revisión: no se publica
        'oculta'        -- dos reportes de personas distintas: oculta y en revisión
    );
exception when duplicate_object then null;
end $$;

-- El default 'publicada' deja publicadas las que ya existen; las del panel las
-- pone 'pendiente' el trigger de abajo.
alter table public.vacantes
    add column if not exists moderacion public.moderacion_vacante not null default 'publicada',
    add column if not exists motivos_moderacion jsonb not null default '[]'::jsonb,
    add column if not exists moderada_en timestamptz,
    add column if not exists revision_avisada_en timestamptz;

do $$
begin
    alter table public.vacantes
        add constraint vacantes_motivos_moderacion_lista
            check (jsonb_typeof(motivos_moderacion) = 'array');
exception when duplicate_object then null;
end $$;

comment on column public.vacantes.moderacion is
    'Si la vacante sale al career site (ADR-022). El panel la lee pero no la escribe: la fija vacantes_moderacion_protegida().';
comment on column public.vacantes.motivos_moderacion is
    'Lista de {regla, cita, senal, gravedad, corregir}: por qué quedó en revisión, rechazada u oculta. El panel se los muestra a la empresa.';
comment on column public.vacantes.revision_avisada_en is
    'Cuándo se avisó a Vector HR (resumen a hola@) de que la vacante espera revisión. Null = falta avisar.';

create index if not exists vacantes_por_moderar_idx
    on public.vacantes (moderacion, created_at)
    where moderacion in ('pendiente', 'en_revision', 'oculta');

-- Con sesión de tenant (el panel por PostgREST) la moderación no se escribe: al
-- crear queda 'pendiente' y al editar lo que el candidato ve vuelve a 'pendiente'.
-- Las skills no cuentan: el career site no las muestra. Sin sesión de tenant —el
-- hr-engine con el rol dueño, o una función security definer llamada sin claims de
-- empresa— se escribe lo que se pida.
create or replace function public.vacantes_moderacion_protegida()
    returns trigger
    language plpgsql
    set search_path = ''
as $$
begin
    if public.empresa_id() is null then
        return new;
    end if;

    if tg_op = 'INSERT' then
        new.moderacion := 'pendiente'::public.moderacion_vacante;
        new.motivos_moderacion := '[]'::jsonb;
        new.moderada_en := null;
        new.revision_avisada_en := null;
        return new;
    end if;

    new.moderacion := old.moderacion;
    new.motivos_moderacion := old.motivos_moderacion;
    new.moderada_en := old.moderada_en;
    new.revision_avisada_en := old.revision_avisada_en;

    if (new.title, new.jd, new.location, new.modality, new.seniority,
        new.salary_min, new.salary_max, new.currency, new.salario_publico)
       is distinct from
       (old.title, old.jd, old.location, old.modality, old.seniority,
        old.salary_min, old.salary_max, old.currency, old.salario_publico) then
        if old.moderacion = 'oculta'::public.moderacion_vacante then
            -- La reportaron: editarla no la saca de la revisión.
            new.moderacion := 'en_revision'::public.moderacion_vacante;
        else
            new.moderacion := 'pendiente'::public.moderacion_vacante;
            new.motivos_moderacion := '[]'::jsonb;
        end if;
        new.moderada_en := null;
        new.revision_avisada_en := null;
    end if;
    return new;
end;
$$;

drop trigger if exists vacantes_moderacion on public.vacantes;
create trigger vacantes_moderacion
    before insert or update on public.vacantes
    for each row execute function public.vacantes_moderacion_protegida();

revoke execute on function public.vacantes_moderacion_protegida() from public, anon, authenticated;

-- ─── 3. Lo público: solo las publicadas ─────────────────────────────────────

-- Igual que 0014, con `moderacion = 'publicada'` y tres columnas al final (create
-- or replace view solo deja agregar columnas al final).
create or replace view public.vacantes_publicas
    with (security_invoker = false)
as
    select v.id, v.slug, v.title, v.jd, v.seniority, v.modality, v.location, v.created_at,
           e.name as empresa_nombre, e.slug as empresa_slug,
           case when v.salario_publico then v.salary_min end as salario_min,
           case when v.salario_publico then v.salary_max end as salario_max,
           case when v.salario_publico then v.currency end as moneda,
           coalesce(
               coalesce((select r.recibidas from privado.aplicaciones_recibidas r
                          where r.vacante_id = v.id), 0)
                   >= public.limite_de_aplicaciones(v.empresa_id),
               false
           ) as cupo_completo,
           e.plan = 'ia' as evalua_con_ia,
           -- Un reclutador independiente nunca lleva la insignia (ADR-022).
           (e.verificada and e.publica_para = 'propia') as empresa_verificada,
           -- Las de un reclutador independiente salen a nombre de quien publica.
           case when e.publica_para = 'clientes' then
               (select p.full_name from public.profiles p
                 where p.empresa_id = e.id
                 order by p.created_at
                 limit 1)
           end as publicada_por,
           case when e.publica_para = 'clientes' then e.linkedin end as linkedin_de_quien_publica
      from public.vacantes v
      join public.empresas e on e.id = v.empresa_id
     where v.status = 'open'
       and v.moderacion = 'publicada';

grant select on public.vacantes_publicas to anon, authenticated;

-- Igual que 0010, más `moderacion = 'publicada'`: no se aplica a una vacante que
-- no está en el career site aunque se conozca su id.
create or replace function public.aplicar_a_vacante(
        p_vacante_id uuid,
        p_full_name  text,
        p_email      text,
        p_cv_path    text default null,
        p_headline   text default null,
        p_linkedin   text default null,
        p_sin_ia     boolean default false
    )
    returns uuid
    language plpgsql
    security definer
    set search_path = ''
as $$
declare
    v_empresa     uuid;
    v_candidato   uuid;
    v_application uuid;
    v_email       text := lower(trim(p_email));
    v_name        text := trim(p_full_name);
begin
    select empresa_id into v_empresa
      from public.vacantes
     where id = p_vacante_id
       and status = 'open'
       and moderacion = 'publicada'::public.moderacion_vacante
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

    insert into public.applications (empresa_id, vacante_id, candidato_id, status, sin_ia)
    values (v_empresa, p_vacante_id, v_candidato, 'applied', coalesce(p_sin_ia, false))
    on conflict (vacante_id, candidato_id) do update
        set sin_ia = applications.sin_ia or excluded.sin_ia
    returning id into v_application;

    return v_application;
end;
$$;

revoke execute on function public.aplicar_a_vacante(uuid, text, text, text, text, text, boolean)
    from public;
grant execute on function public.aplicar_a_vacante(uuid, text, text, text, text, text, boolean)
    to anon, authenticated;

-- El rol del career site (0017): lee y sube CVs solo para las publicadas.
grant select (moderacion) on public.vacantes to career_site;

drop policy if exists vacantes_career_site_abiertas on public.vacantes;
create policy vacantes_career_site_abiertas on public.vacantes
    for select to career_site
    using (status = 'open' and moderacion = 'publicada'::public.moderacion_vacante);

do $$
begin
    if to_regclass('storage.objects') is null then
        raise notice 'schema storage ausente (Postgres plano): se omite la policy de cvs.';
        return;
    end if;

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
                       and v.moderacion = 'publicada'::public.moderacion_vacante
                       and v.empresa_id::text = pg_catalog.split_part(name, '/', 1)
                )
            );
    $pol$;
end $$;

-- ─── 4. Una rechazada no cuenta en el tope ──────────────────────────────────

-- Igual que 0010, sin las rechazadas en activas ni en publicaciones recientes.
create or replace function public.vacantes_respeta_limite_del_plan()
    returns trigger
    language plpgsql
    security definer
    set search_path = ''
as $$
declare
    v_limite    int;
    v_activas   int;
    v_recientes int;
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
       and moderacion <> 'rechazada'::public.moderacion_vacante
       and id <> new.id;

    if v_activas >= v_limite then
        raise exception using
            errcode = 'PT409',
            message = 'limite de vacantes del plan alcanzado',
            detail = format('%s de %s vacantes activas', v_activas, v_limite),
            hint = 'Elimina una vacante activa para publicar otra.';
    end if;

    if tg_op = 'INSERT' or old.publicada_en is null then
        select count(*) into v_recientes
          from public.vacantes
         where empresa_id = new.empresa_id
           and id <> new.id
           and moderacion <> 'rechazada'::public.moderacion_vacante
           and publicada_en > now() - interval '30 days';

        if v_recientes >= v_limite then
            raise exception using
                errcode = 'PT409',
                message = 'limite de publicaciones del plan alcanzado',
                detail = format('%s de %s vacantes publicadas en los últimos 30 días',
                                v_recientes, v_limite),
                hint = 'En el plan gratis se publican cada 30 días tantas vacantes nuevas como vacantes activas permite el plan.';
        end if;
    end if;
    return new;
end;
$$;

create or replace function public.mi_cupo_de_vacantes()
    returns table (
        activas int,
        limite int,
        libres int,
        max_aplicaciones int,
        publicaciones_libres int,
        proxima_publicacion timestamptz
    )
    language sql
    stable
    security definer
    set search_path = ''
as $$
    with e as (
        select public.empresa_id() as id,
               public.limite_de_vacantes(public.empresa_id()) as limite
    ),
    conteo as (
        select
            (select count(*)::int from public.vacantes v, e
              where v.empresa_id = e.id and v.status = 'open'
                and v.moderacion <> 'rechazada'::public.moderacion_vacante) as activas,
            (select count(*)::int from public.vacantes v, e
              where v.empresa_id = e.id
                and v.moderacion <> 'rechazada'::public.moderacion_vacante
                and v.publicada_en > now() - interval '30 days') as recientes,
            (select pg_catalog.min(v.publicada_en) from public.vacantes v, e
              where v.empresa_id = e.id
                and v.moderacion <> 'rechazada'::public.moderacion_vacante
                and v.publicada_en > now() - interval '30 days') as primera_reciente
    )
    select c.activas,
           e.limite,
           case when e.limite is not null then greatest(0, e.limite - c.activas) end,
           public.limite_de_aplicaciones(e.id),
           case when e.limite is not null then greatest(0, e.limite - c.recientes) end,
           case when c.recientes >= e.limite then c.primera_reciente + interval '30 days' end
      from e
      cross join conteo c
     where e.id is not null;
$$;

revoke execute on function public.mi_cupo_de_vacantes() from public, anon;
grant execute on function public.mi_cupo_de_vacantes() to authenticated;

-- ─── 5. Reportes del career site ────────────────────────────────────────────

-- Fuera de PostgREST (esquema `privado`, 0009): nadie los lee desde afuera.
create table if not exists privado.reportes_vacante (
    id         bigint generated always as identity primary key,
    vacante_id uuid not null references public.vacantes (id) on delete cascade,
    motivo     text not null check (char_length(motivo) between 1 and 300),
    -- sha256 de la IP con la sal de abajo: cuenta personas distintas sin guardar la IP.
    ip_hash    text not null check (ip_hash ~ '^[0-9a-f]{64}$'),
    creado_en  timestamptz not null default now(),
    unique (vacante_id, ip_hash)
);

create index if not exists reportes_vacante_por_ip_idx
    on privado.reportes_vacante (ip_hash, creado_en);

comment on table privado.reportes_vacante is
    'Reportes del botón "Reportar vacante" (ADR-022). Uno por IP y vacante; con dos de IPs distintas la vacante se oculta.';

-- Sal secreta del hash de la IP. Vive en la base, así la IP nunca sale de
-- reportar_vacante() ni hay otro secreto que cargar en Vercel.
create table if not exists privado.sal_de_reportes (
    unica boolean primary key default true check (unica),
    valor text not null
);

insert into privado.sal_de_reportes (valor)
values (replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''))
on conflict (unica) do nothing;

-- Cuándo se mandó cada resumen de la cola de revisión a hola@ (tope de correos:
-- Resend gratis da 100 al día y los comparte con Auth).
create table if not exists privado.avisos_de_moderacion (
    id        bigint generated always as identity primary key,
    enviado_en timestamptz not null default now(),
    urgente   boolean not null,
    vacantes  int not null check (vacantes > 0)
);

revoke all on privado.reportes_vacante, privado.sal_de_reportes, privado.avisos_de_moderacion
    from public, anon, authenticated;

-- El botón del career site. Devuelve 'recibido' u 'oculta'. Errores:
--   22023 'vacante no disponible' · 22023 'motivo invalido' · PT429 'demasiados reportes'
create or replace function public.reportar_vacante(
        p_slug   text,
        p_motivo text,
        p_ip     text default null
    )
    returns text
    language plpgsql
    security definer
    set search_path = ''
as $$
declare
    v_vacante   uuid;
    v_motivo    text := trim(coalesce(p_motivo, ''));
    v_hash      text;
    v_recientes int;
    v_fuentes   int;
begin
    if v_motivo = '' or char_length(v_motivo) > 300 then
        raise exception using errcode = '22023', message = 'motivo invalido';
    end if;

    select id into v_vacante
      from public.vacantes
     where slug = p_slug
       and status = 'open'
       and moderacion = 'publicada'::public.moderacion_vacante
       for update;

    if v_vacante is null then
        raise exception using errcode = '22023', message = 'vacante no disponible';
    end if;

    -- Sin IP cuentan todas como una sola persona: no se oculta nada con eso.
    select pg_catalog.encode(
               pg_catalog.sha256(pg_catalog.convert_to(
                   s.valor || '|' || coalesce(nullif(trim(p_ip), ''), 'sin-ip'), 'UTF8')),
               'hex')
      into v_hash
      from privado.sal_de_reportes s;

    select count(*) into v_recientes
      from privado.reportes_vacante
     where ip_hash = v_hash
       and creado_en > now() - interval '1 day';

    if v_recientes >= 10 then
        raise exception using errcode = 'PT429', message = 'demasiados reportes';
    end if;

    insert into privado.reportes_vacante (vacante_id, motivo, ip_hash)
    values (v_vacante, v_motivo, v_hash)
    on conflict (vacante_id, ip_hash) do nothing;

    -- Solo los reportes desde la última moderación: si Vector HR la revisó y la
    -- aprobó, hacen falta dos personas nuevas para volver a ocultarla.
    select count(distinct r.ip_hash) into v_fuentes
      from privado.reportes_vacante r
      join public.vacantes v on v.id = r.vacante_id
     where r.vacante_id = v_vacante
       and r.creado_en > coalesce(v.moderada_en, '-infinity'::timestamptz);

    if v_fuentes >= 2 then
        update public.vacantes
           set moderacion = 'oculta'::public.moderacion_vacante,
               motivos_moderacion = motivos_moderacion || pg_catalog.jsonb_build_array(
                   pg_catalog.jsonb_build_object(
                       'regla', 'reportes',
                       'cita', null,
                       'senal', format('%s personas la reportaron desde el career site', v_fuentes),
                       'gravedad', 'alta',
                       'corregir', null)),
               moderada_en = now(),
               revision_avisada_en = null
         where id = v_vacante;
        return 'oculta';
    end if;
    return 'recibido';
end;
$$;

revoke execute on function public.reportar_vacante(text, text, text) from public, anon, authenticated;
grant execute on function public.reportar_vacante(text, text, text) to career_site;

commit;
