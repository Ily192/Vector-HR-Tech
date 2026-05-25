# sales-engine

> **Cycle 3 (semanas 7-8).**
> FastAPI + Celery — workers Sales (migración de SDR-prospection multi-tenant).

Scaffold pendiente. Bloqueado hasta el cierre de Cycle 1 + Cycle 2.

Plan:

1. Reutilizar la estructura de `hr-engine/` (config, database, monitoring, celery_app idénticos — solo cambia el dominio).
2. Workers a migrar (todos del Portafolio/SDR-prospection):
   - `hunter` — busca leads en Apollo + ZeroBounce verify.
   - `outreach` — sequences vía Reply.io.
   - `closer` — calendly + handoff a humano.
3. UI en `apps/hrbp/sales/` (sub-ruta, mismo cockpit).
4. Tabla `campaigns` ya tiene RLS (`infra/supabase/migrations/0001_initial_schema.sql` — no aún, agregar en `0004_sales_phase1.sql`).

Hosting: mismo patrón que hr-engine (Fly/Railway).
