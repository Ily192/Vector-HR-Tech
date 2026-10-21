-- ════════════════════════════════════════════════════════════════════════════
-- Vortex Ops · 0017_diagnostico_gratuito
-- Fecha: 2026-10-21
-- El diagnóstico gratuito y autoservicio de vectorhrtech.com.
-- Requiere: 0001..0016 (el esquema `privado` es de 0009)
-- ════════════════════════════════════════════════════════════════════════════
--
-- Un prospecto responde unas 11 preguntas y ve qué procesos de HR u operaciones
-- le quitan más tiempo. Antes del detalle deja nombre, empresa, correo y el origen
-- de la campaña (utm). Cada diagnóstico avisa por correo a Vector HR: lo manda el
-- hr-engine (`diagnosticos.avisar`, cada minuto) después de verificar Turnstile.
--
-- Sigue la convención de 0013: la tabla vive en `privado`, que PostgREST no expone
-- y donde `anon` y `authenticated` no tienen permisos, y la única vía de escritura
-- es una RPC de superficie mínima que solo `anon` puede ejecutar. El sitio la llama
-- por su propio dominio (`/api/diagnostico`, que Caddy reenvía al gateway con la
-- clave pública), así que nadie puede leer, cambiar ni borrar un diagnóstico.
--
-- Frenos contra el abuso, en la base para que valgan por cualquier vía: 3 por
-- correo y 5 por IP en una hora, y 300 en total en 24 horas. La IP es la que fija
-- Cloudflare en CF-Connecting-IP (Caddy y el gateway la pasan tal cual). Además
-- hay una regla de rate limiting del WAF de Cloudflare (runbook del VPS).
--
-- Los errores son genéricos a propósito: 22023 para lo inválido y PT429 (PostgREST
-- responde 429) para el freno. No dicen qué campo ni qué límite.
-- ════════════════════════════════════════════════════════════════════════════

begin;

create table if not exists privado.diagnosticos (
    id uuid primary key default gen_random_uuid(),
    creado_en timestamptz not null default now(),
    nombre text not null check (char_length(nombre) between 1 and 120),
    empresa text not null check (char_length(empresa) between 1 and 160),
    correo text not null check (
        char_length(correo) <= 254
        and correo = lower(correo)
        and correo ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'
    ),
    -- utm_source.
    origen text check (char_length(origen) <= 64),
    utm_medium text check (char_length(utm_medium) <= 64),
    utm_campaign text check (char_length(utm_campaign) <= 120),
    respuestas jsonb not null check (
        jsonb_typeof(respuestas) = 'object' and octet_length(respuestas::text) <= 16384
    ),
    -- {version, procesos: [{id, nombre, horasSemana, etapa, horasRecuperablesMes}],
    --  horasRecuperablesMes, horasRecuperablesAnio}, con los procesos de mayor a menor.
    resultado jsonb not null check (
        jsonb_typeof(resultado) = 'object' and octet_length(resultado::text) <= 16384
    ),
    horas_recuperables_mes numeric(7, 1) not null
        check (horas_recuperables_mes >= 0 and horas_recuperables_mes <= 10000),
    ip text check (char_length(ip) <= 64),
    -- Turnstile: hasta 2048 caracteres. Vale una sola vez y 300 s; lo verifica el
    -- hr-engine antes de avisar.
    turnstile_token text check (char_length(turnstile_token) <= 2048),
    -- Lo pone el hr-engine al verificar el token (o al saltarse la verificación sin
    -- secreto). Hace falta guardarlo: un token verificado no se puede volver a verificar.
    verificado_en timestamptz,
    -- No pasó Turnstile: no se avisa.
    descartado_en timestamptz,
    -- Null = falta avisar.
    avisado_en timestamptz,
    intentos_aviso smallint not null default 0 check (intentos_aviso >= 0)
);

-- El barrido del aviso.
create index if not exists diagnosticos_pendientes_idx
    on privado.diagnosticos (creado_en)
    where avisado_en is null and descartado_en is null;
-- Los frenos y el tope diario de avisos.
create index if not exists diagnosticos_correo_idx on privado.diagnosticos (correo, creado_en);
create index if not exists diagnosticos_ip_idx on privado.diagnosticos (ip, creado_en);
create index if not exists diagnosticos_creado_idx on privado.diagnosticos (creado_en);
create index if not exists diagnosticos_avisado_idx
    on privado.diagnosticos (avisado_en) where avisado_en is not null;

alter table privado.diagnosticos enable row level security;
revoke all on privado.diagnosticos from public, anon, authenticated;

-- La única vía de escritura. Recorta y valida todo, y la IP sale de las cabeceras
-- de la petición, nunca de los argumentos.
create or replace function public.registrar_diagnostico(
        p_nombre text,
        p_empresa text,
        p_correo text,
        p_origen text,
        p_utm_medium text,
        p_utm_campaign text,
        p_respuestas jsonb,
        p_resultado jsonb,
        p_horas_recuperables_mes numeric,
        p_turnstile_token text
    )
    returns void
    language plpgsql
    security definer
    set search_path = ''
as $$
declare
    v_nombre text := btrim(coalesce(p_nombre, ''));
    v_empresa text := btrim(coalesce(p_empresa, ''));
    v_correo text := lower(btrim(coalesce(p_correo, '')));
    v_origen text := nullif(btrim(coalesce(p_origen, '')), '');
    v_utm_medium text := nullif(btrim(coalesce(p_utm_medium, '')), '');
    v_utm_campaign text := nullif(btrim(coalesce(p_utm_campaign, '')), '');
    v_token text := nullif(btrim(coalesce(p_turnstile_token, '')), '');
    v_ip text;
begin
    if char_length(v_nombre) not between 1 and 120
       or char_length(v_empresa) not between 1 and 160
       or char_length(v_correo) > 254
       or v_correo !~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'
       or coalesce(char_length(v_origen), 0) > 64
       or coalesce(char_length(v_utm_medium), 0) > 64
       or coalesce(char_length(v_utm_campaign), 0) > 120
       or coalesce(char_length(v_token), 0) > 2048
       or p_respuestas is null or jsonb_typeof(p_respuestas) <> 'object'
       or octet_length(p_respuestas::text) > 16384
       or p_resultado is null or jsonb_typeof(p_resultado) <> 'object'
       or octet_length(p_resultado::text) > 16384
       or p_horas_recuperables_mes is null
       or p_horas_recuperables_mes not between 0 and 10000 then
        raise exception 'diagnóstico inválido' using errcode = '22023';
    end if;

    -- PostgREST deja las cabeceras en `request.headers`, con los nombres en minúsculas.
    v_ip := left(nullif(current_setting('request.headers', true), '')::json ->> 'cf-connecting-ip', 64);

    -- Uno a la vez, para que dos peticiones simultáneas no se salten el freno. Son
    -- pocas al día: la espera no se nota.
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtext('privado.diagnosticos'));
    if (select count(*) from privado.diagnosticos
         where correo = v_correo and creado_en > now() - interval '1 hour') >= 3
       or (select count(*) from privado.diagnosticos
            where ip is not distinct from v_ip and creado_en > now() - interval '1 hour') >= 5
       or (select count(*) from privado.diagnosticos
            where creado_en > now() - interval '1 day') >= 300 then
        raise exception 'demasiados diagnósticos; intenta más tarde' using errcode = 'PT429';
    end if;

    insert into privado.diagnosticos
        (nombre, empresa, correo, origen, utm_medium, utm_campaign, respuestas, resultado,
         horas_recuperables_mes, ip, turnstile_token)
    values
        (v_nombre, v_empresa, v_correo, v_origen, v_utm_medium, v_utm_campaign, p_respuestas,
         p_resultado, round(p_horas_recuperables_mes, 1), v_ip, v_token);
end;
$$;

revoke execute on function public.registrar_diagnostico(
    text, text, text, text, text, text, jsonb, jsonb, numeric, text
) from public, anon, authenticated;
grant execute on function public.registrar_diagnostico(
    text, text, text, text, text, text, jsonb, jsonb, numeric, text
) to anon;

commit;
