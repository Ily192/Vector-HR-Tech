-- ════════════════════════════════════════════════════════════════════════════
-- Vortex Ops · 0012_slug_unico_en_el_career_site
-- Fecha: 2026-10-20
-- El slug de una vacante es único en todo el career site, no solo en su empresa.
-- Requiere: 0001..0011
-- ════════════════════════════════════════════════════════════════════════════
--
-- El career site es uno solo para todas las empresas (ADR-017 §5) y la vacante
-- vive en `/vacantes/<slug>`. 0001 solo exigía `unique (empresa_id, slug)`: dos
-- empresas con "analista-de-datos" chocaban en la misma URL y el career site
-- mostraba cualquiera de las dos. El panel le añade un sufijo al slug y, si aun
-- así choca (23505), prueba con otro.
-- ════════════════════════════════════════════════════════════════════════════

begin;

create unique index if not exists vacantes_slug_unico on public.vacantes (slug);

commit;
