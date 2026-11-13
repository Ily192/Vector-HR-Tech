-- ════════════════════════════════════════════════════════════════════════════
-- Fluve AI · 0020_recordatorio_de_postulados
-- Fecha: 2026-11-13
-- Un solo correo a la empresa cuando junta más de 5 postulados sin revisar.
-- Requiere: 0001..0019
-- ════════════════════════════════════════════════════════════════════════════
--
-- Ilyra lo pidió así: "solo cuando ya tengan más de 5 postulados a sus ofertas y
-- que llegue un aviso cuando realmente se necesite avisarle a la persona si no ha
-- revisado el panel". Nunca un correo por postulación ni al candidato (ADR-023).
--
-- 1. `privado.postulaciones_vistas`: cuándo vio la empresa las postulaciones de
--    cada vacante. La pone `marcar_postulaciones_vistas()`, que el panel llama al
--    abrir "Ver postulaciones". Lo que llegó después cuenta como sin revisar.
-- 2. `privado.recordatorios_de_postulados`: cada recordatorio mandado y a cuántas
--    personas. El hr-engine (rol dueño) lo lee para no repetir el aviso hasta que
--    la empresa entre y para no pasarse del tope diario: Resend gratis da 100
--    correos al día y los comparte con los códigos de acceso de Auth.
--
-- Ninguna de las dos guarda datos de candidatos: solo fechas, la vacante y cuántos.
-- ════════════════════════════════════════════════════════════════════════════

begin;

-- ─── 1. Lo que la empresa ya vio ────────────────────────────────────────────

create table if not exists privado.postulaciones_vistas (
    vacante_id uuid primary key references public.vacantes (id) on delete cascade,
    empresa_id uuid not null references public.empresas (id) on delete cascade,
    vistas_en timestamptz not null default now()
);

create index if not exists postulaciones_vistas_empresa_idx
    on privado.postulaciones_vistas (empresa_id, vistas_en desc);

alter table privado.postulaciones_vistas enable row level security;
revoke all on privado.postulaciones_vistas from public, anon, authenticated;

-- La empresa sale del JWT y la vacante tiene que ser suya: con el id de otra no se
-- marca nada y devuelve false. Solo HR y Dirección, los que ven las postulaciones
-- en el panel (policy `applications_tenant_read`, 0004); Vector HR (SuperAdmin) no
-- cuenta como "la empresa ya las vio".
-- `on conflict do update`: Postgres 17, INSERT, "ON CONFLICT DO UPDATE updates the
-- existing row that conflicts with the row proposed for insertion"
-- (https://www.postgresql.org/docs/17/sql-insert.html).
create or replace function public.marcar_postulaciones_vistas(p_vacante uuid)
    returns boolean
    language plpgsql
    security definer
    set search_path = ''
as $$
declare
    marcadas bigint;
begin
    if public.empresa_id() is null
       or public.app_role() not in ('HR', 'Director') then
        raise exception 'solo HR o Dirección de la empresa marcan sus postulaciones como vistas'
            using errcode = '42501';
    end if;

    insert into privado.postulaciones_vistas (vacante_id, empresa_id, vistas_en)
    select v.id, v.empresa_id, now()
      from public.vacantes v
     where v.id = p_vacante
       and v.empresa_id = public.empresa_id()
    on conflict (vacante_id) do update set vistas_en = excluded.vistas_en;

    -- GET DIAGNOSTICS … ROW_COUNT: "the number of rows processed by the most recent
    -- SQL command" (https://www.postgresql.org/docs/17/plpgsql-statements.html).
    get diagnostics marcadas = row_count;
    return marcadas > 0;
end;
$$;

revoke execute on function public.marcar_postulaciones_vistas(uuid) from public, anon;
grant execute on function public.marcar_postulaciones_vistas(uuid) to authenticated;

-- ─── 2. Los recordatorios que salieron ──────────────────────────────────────

create table if not exists privado.recordatorios_de_postulados (
    id bigint generated always as identity primary key,
    empresa_id uuid not null references public.empresas (id) on delete cascade,
    -- Cuántos postulados sin revisar tenía al mandarlo, y a cuántas personas fue:
    -- el tope diario cuenta correos, no empresas.
    postulados int not null check (postulados > 0),
    destinatarios int not null check (destinatarios > 0),
    enviado_en timestamptz not null default now()
);

create index if not exists recordatorios_de_postulados_empresa_idx
    on privado.recordatorios_de_postulados (empresa_id, enviado_en desc);
create index if not exists recordatorios_de_postulados_enviado_idx
    on privado.recordatorios_de_postulados (enviado_en);

alter table privado.recordatorios_de_postulados enable row level security;
revoke all on privado.recordatorios_de_postulados from public, anon, authenticated;

commit;
