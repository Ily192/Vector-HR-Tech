-- ════════════════════════════════════════════════════════════════════════════
-- Vortex Ops · 0013_interes_en_la_ia
-- Fecha: 2026-10-20
-- La empresa gratuita pide los servicios de IA desde el panel.
-- Requiere: 0001..0012
-- ════════════════════════════════════════════════════════════════════════════
--
-- Es el evento de venta del plan gratis: "Evaluarlos con IA" en el gancho del
-- pipeline y "Quiero saber más" en Crear empleo (ADR-019 §14, señales de venta).
-- Vector HR lo ve en `privado.intereses_en_ia` y escribe a la empresa.
--
-- Solo guarda quién pidió qué y desde dónde: ningún dato de candidatos.
-- ════════════════════════════════════════════════════════════════════════════

begin;

create table if not exists privado.intereses_en_ia (
    id bigint generated always as identity primary key,
    empresa_id uuid not null references public.empresas (id) on delete cascade,
    user_id uuid,
    origen text not null check (origen in ('pipeline', 'crear-empleo')),
    creado_en timestamptz not null default now()
);

create index if not exists intereses_en_ia_empresa_idx on privado.intereses_en_ia (empresa_id, creado_en);

alter table privado.intereses_en_ia enable row level security;
revoke all on privado.intereses_en_ia from public, anon, authenticated;

-- La empresa y la persona salen del JWT, nunca de los argumentos.
create or replace function public.registrar_interes_en_ia(p_origen text)
    returns void
    language plpgsql
    security definer
    set search_path = ''
as $$
begin
    if public.empresa_id() is null
       or public.app_role() not in ('HR', 'Director', 'SuperAdmin') then
        raise exception 'solo HR o Dirección de una empresa pueden pedir los servicios de IA'
            using errcode = '42501';
    end if;
    insert into privado.intereses_en_ia (empresa_id, user_id, origen)
    values (public.empresa_id(), auth.uid(), p_origen);
end;
$$;

revoke execute on function public.registrar_interes_en_ia(text) from public, anon;
grant execute on function public.registrar_interes_en_ia(text) to authenticated;

commit;
