# Supabase — schema & migrations

## Local

Dos caminos, y conviene no mezclarlos:

**A. Supabase CLI** — el más fiel a producción, porque trae `auth`, Storage y
los roles reales (`anon`, `authenticated`, `service_role`).

```bash
supabase init        # solo primera vez en el proyecto
supabase start       # arranca Postgres local + Auth + Storage
supabase db reset    # aplica migrations + seed
```

URL local: `postgresql://postgres:postgres@localhost:54322/postgres`
Studio:   http://localhost:54323

**B. docker compose** — Postgres + Redis + hr-engine, sin Auth ni Storage.

```bash
docker compose -f infra/docker/docker-compose.dev.yml up -d
```

URL local: `postgresql://vortex:vortex@localhost:5432/vortex_dev`

El compose monta `infra/docker/initdb/00_supabase_shim.sql` **antes** de las
migraciones. Ese shim crea el schema `auth`, `auth.users`, `auth.uid()` y los
roles que las migraciones referencian y que un Postgres plano no tiene. Sin él
la primera migración falla y el entrypoint de Postgres aborta la
inicialización: el contenedor nunca llega a tener esquema.

Al añadir una migración nueva hay que montarla también en el compose, con su
prefijo numérico. Los scripts del entrypoint corren en orden alfabético y solo
en la primera inicialización del volumen; para reaplicar hay que borrarlo
(`docker compose ... down -v`).

## Producción (Supabase Cloud)

```bash
supabase link --project-ref <YOUR_REF>
supabase db push     # aplica migrations pendientes
```

No hay migraciones de rollback. La estrategia es *forward-only*: si `000N`
sale mal, se corrige con `000N+1`. Antes de aplicar en producción hay que
tener PITR o un dump reciente, porque no existe otro camino de vuelta.

## Migrations

| Versión | Descripción |
|---|---|
| `0001_initial_schema.sql` | Tenant root + HR domain core (vacantes, candidatos, applications) + runs/activity_log + RLS + helpers `public.empresa_id()` / `public.app_role()` |
| `0002_hr_phase2.sql` | psicometricos · entrevistas · constancias + RLS + trigger anti tenant-drift |
| `0003_auth_hooks.sql` | tabla `invitations` + `handle_new_user` trigger + `custom_access_token_hook` (JWT claims) |
| `0004_security_hardening.sql` | Cierre de las vías de escalada multi-tenant halladas en la auditoría previa al primer deploy |
| `0005_apply_flow.sql` | Bucket `cvs` + `aplicar_a_vacante()`: la única vía por la que un candidato entra al pipeline |

## RLS — reglas vigentes

- **Toda tabla con `empresa_id`** filtra por `public.empresa_id()`, y las que
  contienen PII (`candidatos`, `applications`, `entrevistas`) además exigen rol
  `HR`/`Director` para escribir. Un `Colaborador` no lee la base de candidatos.
- **`vacantes`**: `anon` no tiene acceso a la tabla. El career-site lee la vista
  `vacantes_publicas`, que expone solo las vacantes `open` y omite `icp_text`,
  `icp_embedding`, las bandas salariales y `empresa_id`.
- **`psicometricos`**: `anon` no tiene acceso a la tabla. El candidato usa
  `get_psicometrico_by_token()` y `submit_psicometrico()`, dos funciones
  `security definer` de superficie mínima. El token se guarda hasheado
  (sha256), así que un dump ya no permite suplantar a nadie.
- **`constancias`** son visibles para el `profile_id` dueño + HR/Director del
  tenant.
- **Privilegio de plataforma**: vive en la tabla `platform_admins`, no en
  `profiles.role`. Ningún usuario `authenticated` puede escribirla.
- **`activity_log`** es append-only: triggers bloquean UPDATE, DELETE y
  TRUNCATE.
- **`force row level security` NO está activo**, y la razón está documentada en
  `0004` §9: FORCE alcanza también al owner cuando ejecuta una función
  `security definer` o una vista con `security_invoker = false`, que es
  exactamente cómo está construido todo el acceso público de este esquema. Con
  FORCE, el career-site no listaría vacantes y ningún candidato podría aplicar.

Tests automatizados de aislamiento multi-tenant en
`services/hr-engine/tests/security/test_rls.py` (CI job `rls-tests`). Incluyen
casos de regresión para cada vía de escalada cerrada en `0004`.

## JWT custom claims

El JWT de Supabase Auth incluye:

```json
{ "app_metadata": { "empresa_id": "<uuid>", "app_role": "HR" } }
```

Dos detalles que importan:

- El rol viaja como **`app_role`**, no como `role`. `role` es un claim
  reservado: PostgREST hace `SET LOCAL ROLE` con él, así que escribir `"HR"` ahí
  hacía fallar toda petición autenticada con `42704: role "HR" does not exist`.
- Va bajo **`app_metadata`**, no `user_metadata`, porque este último lo puede
  editar el propio usuario con `supabase.auth.updateUser()`.

Poblados automáticamente por `custom_access_token_hook` (ver
`0003_auth_hooks.sql`). Para activarlo en Supabase Cloud: **Dashboard →
Authentication → Hooks → Custom Access Token** y apuntar a
`public.custom_access_token_hook`. **Si no se activa, todas las policies de HR
deniegan** — no es un paso opcional.

## Alta de usuarios

No hay auto-registro. `handle_new_user` exige un `invite_token` válido en el
metadata del signup y saca `empresa_id` y `role` de la tabla `invitations`,
nunca del metadata.

La versión anterior sí los sacaba del metadata, que es el `options.data` de
`supabase.auth.signUp()` y lo controla el cliente al 100%: cualquiera con la
anon key —pública por diseño— podía darse de alta como `SuperAdmin` dentro del
tenant que eligiera. El `empresa_id` de la víctima ni siquiera había que
adivinarlo, porque `vacantes` lo exponía a `anon`.

## Tenant drift guard

Dos capas:

1. **FK compuestas `(id, empresa_id)`** entre `applications` y sus padres, y
   entre `psicometricos`/`entrevistas` y `applications`. Las FK simples se
   verifican con un scan interno que ignora RLS, así que antes se podía crear
   una `application` del tenant A apuntando a un candidato del tenant B. El
   motor ahora lo impide, también para `service_role`.
2. **Trigger `enforce_empresa_id_from_application`** en INSERT y en UPDATE
   (antes solo INSERT, así que un UPDATE podía mover una fila de tenant).

## Flujo público de aplicación

El candidato nunca escribe directo en la base ni en Storage:

1. La Server Action del career-site recibe el formulario y el fichero.
2. Sube el CV con la **service_role key** a `cvs/{empresa_id}/{candidato_id}/…`.
   No hay policy de INSERT sobre `storage.objects`: dársela a `anon` convertiría
   el bucket en un dropbox público.
3. Llama a `public.aplicar_a_vacante()`, que valida la vacante (debe estar
   `open`), el email, y que la ruta del CV cuelgue del tenant correcto.

**Falta la capa anti-abuso.** `aplicar_a_vacante()` es ejecutable por `anon` e
inserta filas, así que necesita rate limiting o captcha en la Server Action
antes de exponerse al público.

## Pendiente

- **Retención y borrado (LGPD / Habeas Data)**: `docs/08_SECURITY_AND_COMPLIANCE.md`
  promete retención por tipo de dato y endpoints de export/erasure; el esquema
  no tiene ni `deleted_at`, ni `retention_until`, ni jobs de purga.
- **Cifrado de columna** para `psicometricos.raw_answers` y
  `entrevistas.transcript`, que hoy están en claro.
