# ADR-004: Supabase RLS como última línea de defensa multi-tenant

- **Status:** Accepted
- **Date:** 2026-05-08
- **Tags:** security, multi-tenant

## Context

Multi-tenancy SaaS exige aislamiento perfecto entre clientes. Una sola query mal escrita = breach.

## Decision

**Defensa en profundidad** en 3 capas:

1. **App-level guard:** middleware `tenant_guard` en FastAPI extrae `empresa_id` del JWT y lo inyecta en queries.
2. **DB-level RLS (Supabase Postgres):** política `using (empresa_id = auth.empresa_id())` en cada tabla con `empresa_id`.
3. **Test gate:** suite dedicada `tests/security/test_rls.py` que con JWT de tenant A intenta leer datos de tenant B → debe fallar. Corre en cada PR + nightly paranoid scan.

JWT incluye custom claim `empresa_id` poblado por trigger Supabase post-login.

## Consequences

**Positivas:** aun si la app falla, la DB rechaza; auditable por DBA.
**Negativas:** ~5-10% overhead en queries; obliga disciplina al hacer migrations (RLS por defecto).

**Mitigación overhead:** índices sobre `empresa_id` en toda tabla con RLS.

## Alternatives considered

- **Schema por tenant:** descartado para Pro/Scale (operacionalmente caro). Sí para Enterprise.
- **DB por tenant:** absurdo en costo a escala.
- **Solo app-level:** un bug = leak. Inaceptable.
