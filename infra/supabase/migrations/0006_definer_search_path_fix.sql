-- ════════════════════════════════════════════════════════════════════════════
-- Vortex Ops · 0006_definer_search_path_fix
-- Fecha: 2026-09-08
-- TRES defectos encontrados al ejecutar por PRIMERA VEZ los tests de RLS contra
-- un Postgres real (pgvector/pgvector:pg15, el mismo contenedor que usa CI).
-- Requiere: 0001..0005
-- ════════════════════════════════════════════════════════════════════════════
--
-- Contexto: hasta hoy las migraciones 0001-0005 solo se habian validado
-- sintacticamente con libpg_query. Parsear no es ejecutar.
--
-- OJO CON EL NOMBRE DEL FICHERO: describe a dos de los tres. §1 y §3 si son de
-- resolucion de nombres bajo `search_path` fijado. §2 NO: la policy de
-- `empresas` ya invocaba `public.is_platform_admin()` totalmente calificada, y
-- lo que le falta es la clausula `TO`. Es un fallo de PRIVILEGIOS (42501), y su
-- fix no califica nada — anade `to authenticated`. Agruparlos bajo una sola
-- tesis es comodo y es falso.
--
-- Lo que si comparten los tres es que solo aparecen al EJECUTAR: ninguno es
-- visible para un analisis estatico sin catalogo delante, y esta migracion —como
-- las anteriores— se aplica sin un solo warning.
--
-- Los tres son fallos de DISPONIBILIDAD, no de confidencialidad: nada se filtra,
-- pero dos rutas del producto devuelven error en vez de funcionar.


-- ════════════════════════════════════════════════════════════════════════════
-- 1. submit_psicometrico: cast a un tipo sin calificar bajo search_path vacio
-- ════════════════════════════════════════════════════════════════════════════
--
-- 0004 §3 movio el flujo publico del test psicometrico a dos funciones
-- `security definer` con `set search_path = ''`, que es la defensa correcta
-- contra el shadoweo de objetos por un atacante con CREATE sobre `public`.
--
-- El cuerpo de `submit_psicometrico` quedo con dos casts sin calificar:
--
--     status = case when p_finish then 'completed'::psicometrico_status
--                   else 'in_progress'::psicometrico_status end
--
-- El cuerpo de una funcion plpgsql se resuelve en EJECUCION, con el search_path
-- de la propia funcion — que aqui esta vacio. `psicometrico_status` vive en
-- `public`, asi que la resolucion falla:
--
--     ERROR: type "psicometrico_status" does not exist
--
-- Efecto real: NINGUN candidato podia enviar su test psicometrico. La funcion
-- es la unica via de escritura (0004 revoco `psicometricos` a `anon`), asi que
-- el flujo entero estaba muerto y la primera llamada reventaba.
--
-- Por que no se vio antes: la clausula RETURNS de `get_psicometrico_by_token`
-- tambien nombra el tipo sin calificar, pero esa SI se resuelve en tiempo de
-- CREATE con el search_path de la sesion que aplica la migracion. La migracion
-- se creaba sin un solo warning. Solo el cuerpo falla, y solo al invocarlo.

create or replace function public.submit_psicometrico(
        p_token   text,
        p_answers jsonb,
        p_big5    jsonb default null,
        p_finish  boolean default false
    )
    returns uuid
    language plpgsql
    security definer
    set search_path = ''
as $fn$
declare
    target public.psicometricos%rowtype;
begin
    select * into target
      from public.psicometricos
     where token_hash = encode(sha256(p_token::bytea), 'hex')
       and status in ('pending', 'in_progress')
       and expires_at > now()
     for update;

    if not found then
        raise exception using
            errcode = '22023',
            message = 'token invalido, ya usado o expirado';
    end if;

    update public.psicometricos
       set raw_answers = coalesce(p_answers, raw_answers),
           big5_openness = coalesce((p_big5 ->> 'openness')::numeric, big5_openness),
           big5_conscientiousness = coalesce((p_big5 ->> 'conscientiousness')::numeric, big5_conscientiousness),
           big5_extraversion = coalesce((p_big5 ->> 'extraversion')::numeric, big5_extraversion),
           big5_agreeableness = coalesce((p_big5 ->> 'agreeableness')::numeric, big5_agreeableness),
           big5_neuroticism = coalesce((p_big5 ->> 'neuroticism')::numeric, big5_neuroticism),
           started_at = coalesce(started_at, now()),
           -- Calificado con `public.`: sin esto el cast no resuelve en runtime.
           status = case when p_finish then 'completed'::public.psicometrico_status
                         else 'in_progress'::public.psicometrico_status end,
           completed_at = case when p_finish then now() else completed_at end,
           updated_at = now()
     where id = target.id;

    return target.id;
end;
$fn$;

revoke execute on function public.submit_psicometrico(text, jsonb, jsonb, boolean) from public;
grant execute on function public.submit_psicometrico(text, jsonb, jsonb, boolean) to anon, authenticated;

-- Misma calificacion en la firma de la funcion de lectura. Aqui no cambia el
-- comportamiento (RETURNS se resuelve en CREATE), pero deja de depender del
-- search_path de quien aplique la migracion.
drop function if exists public.get_psicometrico_by_token(text);
create function public.get_psicometrico_by_token(p_token text)
    returns table (
        id uuid,
        status public.psicometrico_status,
        started_at timestamptz,
        expires_at timestamptz
    )
    language sql
    stable
    security definer
    set search_path = ''
as $fn$
    select p.id, p.status, p.started_at, p.expires_at
      from public.psicometricos p
     where p.token_hash = encode(sha256(p_token::bytea), 'hex')
       and p.status in ('pending', 'in_progress')
       and p.expires_at > now();
$fn$;

revoke execute on function public.get_psicometrico_by_token(text) from public;
grant execute on function public.get_psicometrico_by_token(text) to anon, authenticated;


-- ════════════════════════════════════════════════════════════════════════════
-- 2. empresas: la policy de platform admin se evaluaba tambien para `anon`
-- ════════════════════════════════════════════════════════════════════════════
--
-- 0004 §1 creo `is_platform_admin()` con el grant correcto —
-- `revoke ... from public, anon; grant ... to authenticated` — y una policy
-- que la invoca:
--
--     create policy empresas_platform_admin_all on public.empresas
--         for all using ((select public.is_platform_admin())) ...
--
-- La policy no lleva clausula `TO`, asi que su rol implicito es PUBLIC y
-- Postgres la evalua para CUALQUIER rol, `anon` incluido. Como `anon` no tiene
-- EXECUTE sobre la funcion, un `select from empresas` sin sesion no devuelve
-- cero filas: aborta.
--
--     ERROR: permission denied for function is_platform_admin
--
-- Verificado contra la base: de las 9 relaciones sobre las que `anon` conserva
-- grants, `empresas` es la UNICA que revienta; las otras 8 devuelven 0 filas.
--
-- Efecto real: PostgREST traduce eso a un 500 en `/rest/v1/empresas` en vez del
-- `[]` que corresponde. No hay fuga de datos — el error ocurre ANTES de leer
-- ninguna fila — pero es una ruta rota, y ruido de 5xx que enmascara incidentes
-- de verdad. Peor: cualquier policy futura que llame a esta funcion sobre una
-- tabla que `anon` toque heredaria el mismo error.
--
-- Fix: acotar la policy a `authenticated`, que es el unico rol que puede
-- satisfacerla (`is_platform_admin()` se apoya en `auth.uid()`, que para `anon`
-- es NULL). Es ademas la recomendacion de Supabase para toda policy: sin `TO`,
-- el planner las evalua para roles que jamas podrian pasarlas.
--
-- NOTA: las 21 policies del esquema estan hoy sin `TO`. Solo esta rompe, porque
-- es la unica que invoca una funcion con EXECUTE restringido. Acotar las otras
-- 20 es higiene pendiente, no un fallo — ver next-steps § deuda tecnica.

drop policy if exists empresas_platform_admin_all on public.empresas;
create policy empresas_platform_admin_all on public.empresas
    for all
    to authenticated
    using ((select public.is_platform_admin()))
    with check ((select public.is_platform_admin()));


-- ════════════════════════════════════════════════════════════════════════════
-- 3. enforce_empresa_id_from_application: hereda el search_path de quien dispara
-- ════════════════════════════════════════════════════════════════════════════
--
-- El mismo fallo que §1, pero por una via que no se ve leyendo la funcion.
--
-- 0002 definio este trigger sin `set search_path`, con `from applications` sin
-- calificar. Eso funciona mientras lo dispare una sentencia normal, porque
-- entonces corre con el search_path de la sesion, que incluye `public`.
--
-- 0004 §5 lo extendio — correctamente — a BEFORE UPDATE de `psicometricos`,
-- para que un UPDATE no pudiera mover una fila a otro tenant. Pero el unico
-- UPDATE del flujo publico lo hace `submit_psicometrico()`, que es
-- `security definer` con `set search_path = ''`.
--
-- Una funcion de trigger sin search_path propio NO tiene uno por defecto:
-- hereda el que este activo en ese momento. Disparada desde dentro de la
-- funcion definer, ese search_path es el vacio, y la resolucion falla:
--
--     ERROR: relation "applications" does not exist
--
-- Efecto real: aun con §1 arreglado, `submit_psicometrico()` seguia reventando
-- — ahora dentro del trigger en vez de en el cast. Los dos bugs estaban en
-- serie sobre la misma linea de codigo, asi que arreglar uno solo no habria
-- devuelto el flujo a la vida. Se encontro justamente porque el primer fix
-- destapo el segundo al re-ejecutar la suite.
--
-- Fijar el search_path aqui es ademas lo correcto en si mismo: un trigger que
-- resuelve nombres segun quien lo dispara es fragil por definicion.

create or replace function public.enforce_empresa_id_from_application()
    returns trigger
    language plpgsql
    set search_path = ''
as $fn$
declare
    parent_empresa uuid;
begin
    select empresa_id into parent_empresa
      from public.applications
     where id = new.application_id;

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
$fn$;
