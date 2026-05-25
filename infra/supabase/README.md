# Supabase — schema & migrations

## Local (con Supabase CLI)

```bash
supabase init        # solo primera vez en el proyecto
supabase start       # arranca Postgres local + Auth + Storage
supabase db reset    # aplica migrations + seed
```

URL local: `postgresql://postgres:postgres@localhost:54322/postgres`
Studio:   http://localhost:54323

## Producción (Supabase Cloud)

```bash
supabase link --project-ref <YOUR_REF>
supabase db push     # aplica migrations pendientes
```

## Migrations

| Versión | Descripción |
|---|---|
| `0001_initial_schema.sql` | Tenant root + HR domain core (vacantes, candidatos, applications) + runs/activity_log + RLS |
| `0002_hr_phase2.sql` | psicometricos · entrevistas · constancias + RLS + trigger anti tenant-drift |
| `0003_auth_hooks.sql` | `handle_new_user` trigger + `custom_access_token_hook` (JWT claims) + `set_tenant_context` helper |

## RLS — Reglas

- **Toda tabla con `empresa_id`** tiene política `tenant_isolation` por default.
- **`vacantes` con `status='open'`** es lectura pública (career-site).
- **`psicometricos` con status `pending`/`in_progress` y no expirado** es lectura/update pública por token (candidato responde el test sin auth).
- **`constancias`** son visibles para el `profile_id` dueño + HR/Director/SuperAdmin del tenant.
- **SuperAdmin** tiene bypass auditado en `empresas`.
- **`activity_log`** es append-only via trigger (UPDATE/DELETE bloqueados).

Tests automatizados de aislamiento multi-tenant en `services/hr-engine/tests/security/test_rls.py` (CI job `rls-tests`).

## JWT custom claims

El JWT de Supabase Auth incluye:

```json
{ "empresa_id": "<uuid>", "role": "HR" }
```

Poblados automáticamente por `custom_access_token_hook` (ver `0003_auth_hooks.sql`).
Para activarlo en Supabase Cloud: **Dashboard → Authentication → Hooks →
Custom Access Token** y apuntar a `public.custom_access_token_hook`.

## Tenant drift guard

Tablas hijas (`psicometricos`, `entrevistas`) tienen trigger `enforce_empresa_id_from_application`
que rechaza inserts donde `empresa_id` no matchea el de la `application` padre.
Defensa en profundidad incluso si bypasea RLS (service_role).
