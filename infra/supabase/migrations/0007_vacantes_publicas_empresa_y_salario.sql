-- ════════════════════════════════════════════════════════════════════════════
-- Vortex Ops · 0007_vacantes_publicas_empresa_y_salario
-- Fecha: 2026-10-16
-- Requiere: 0001..0006
-- ════════════════════════════════════════════════════════════════════════════
--
-- ADR-017: el career site es uno solo para todas las empresas, así que cada
-- vacante pública tiene que decir de qué empresa es. Y el candidato quiere ver
-- el salario, pero 0004 lo sacó de la vista a propósito: `salary_min/max` son la
-- banda INTERNA de la empresa, no lo que quiere publicar.
--
-- 1. `vacantes.salario_publico`: la empresa decide si publica el rango. Por
--    defecto, no. La vista solo lo enseña si está a `true`; si no, NULL.
--    `salary_min`/`salary_max` siguen sin existir como columnas de la vista
--    (lo comprueba test_public_view_hides_commercial_columns).
-- 2. Nombre y slug de la empresa, nunca su `empresa_id` (ver 0004 §4).
--
-- `create or replace view` solo puede añadir columnas al final, sin tocar las
-- anteriores: el orden de 0004 se conserva.

alter table public.vacantes
    add column if not exists salario_publico boolean not null default false;

comment on column public.vacantes.salario_publico is
    'Si es true, vacantes_publicas expone salary_min/max/currency como salario publicado. Por defecto la banda es interna.';

create or replace view public.vacantes_publicas
with (security_invoker = false) as
    select v.id, v.slug, v.title, v.jd, v.seniority, v.modality, v.location, v.created_at,
           e.name as empresa_nombre,
           e.slug as empresa_slug,
           case when v.salario_publico then v.salary_min end as salario_min,
           case when v.salario_publico then v.salary_max end as salario_max,
           case when v.salario_publico then v.currency end as moneda
      from public.vacantes v
      join public.empresas e on e.id = v.empresa_id
     where v.status = 'open';

grant select on public.vacantes_publicas to anon, authenticated;
