# ADR-015: Mover la identidad de tenant a `app_metadata` y sacar el privilegio de plataforma de `profiles`

- **Status:** Accepted
- **Date:** 2026-09-07
- **Decider:** Ilyra
- **Tags:** security, multi-tenant, auth
- **Complementa:** [ADR-004](004-supabase-rls-defense-in-depth.md)

## Context

ADR-004 estableció RLS como última línea de defensa. La implementación
(`0001`–`0003`) siguió esa decisión, pero una auditoría previa al primer deploy
encontró que el *mecanismo de identidad* sobre el que RLS se apoyaba tenía tres
defectos que lo anulaban por completo. Ninguna de las migraciones se había
aplicado nunca a un proyecto real, así que se corrigieron en su sitio y el
resto se cerró en `0004`.

**1. El alta de usuarios confiaba en datos del cliente.** `handle_new_user`
derivaba `empresa_id` y `role` de `raw_user_meta_data`, que es literalmente el
`options.data` de `supabase.auth.signUp()`. GoTrue no lo valida, y el trigger
corre `security definer`, así que bypassa RLS. Con la anon key —pública por
diseño— cualquiera podía darse de alta como `SuperAdmin` dentro del tenant que
eligiera. El `empresa_id` de la víctima ni siquiera había que adivinarlo:
`vacantes` lo exponía a `anon`.

**2. El rol viajaba en un claim reservado.** El hook escribía
`claims.role = 'HR'`. Pero `role` es el claim que PostgREST usa para hacer
`SET LOCAL ROLE` en cada request: intentaría `set role "HR"` y fallaría con
`42704`. Los dos estados posibles del sistema eran "hook activo → toda petición
autenticada rota" y "hook inactivo → `auth.role()` devuelve `authenticated`, que
no está en ningún `in (...)` de las policies, y todo deniega".

**3. Los helpers vivían en el schema `auth`.** `create or replace function
auth.role()` aborta en Supabase Cloud con `must be owner of function role`: esa
función es propiedad de `supabase_auth_admin`. Es decir, `0001` no se podía
aplicar. Y si se hubiera podido, redefinir `auth.role()` habría roto en
silencio las policies de Supabase Storage, que la usan para distinguir `anon`
de `authenticated` —justo el bucket de CVs que el Cycle 1 necesita—. Además las
funciones no fijaban `search_path`, y se evalúan *dentro* de cada policy: quien
pudiera crear `public.current_setting` devolvería el `empresa_id` que quisiera.

Como agravante, `SuperAdmin` era un valor de `profiles.role` —una columna por
tenant— pero otorgaba `FOR ALL` sobre **todas** las empresas. Y
`profiles_hr_manage` dejaba que un HR de cualquier cliente promoviera a un
cómplice a `SuperAdmin`. Cadena completa: HR de un cliente → acceso global de
lectura, escritura y borrado sobre todos los demás clientes.

## Decision

**La identidad de tenant viaja en `app_metadata`, la establece el servidor, y el
privilegio de plataforma no es un rol de tenant.**

1. **Claims bajo `app_metadata`, con nombre propio.** El JWT lleva
   `app_metadata.empresa_id` y `app_metadata.app_role`. Nunca `role` en la raíz
   (reservado por PostgREST) ni nada en `user_metadata` (lo edita el usuario con
   `updateUser()`).

2. **Helpers en `public`, con `search_path` vacío.** `public.empresa_id()` y
   `public.app_role()`, `security invoker`, `set search_path = ''`, todo
   calificado con `pg_catalog`. Se invocan en las policies como
   `(select public.empresa_id())` para que Postgres las evalúe una vez por query
   (InitPlan) en lugar de una vez por fila.

3. **El alta requiere invitación.** Nueva tabla `invitations`, escrita solo por
   HR/Director del propio tenant, con el token hasheado. `handle_new_user` no
   lee `empresa_id` ni `role` del metadata: los saca de la invitación, valida
   que el email coincida y la marca como consumida. Del metadata solo se acepta
   `full_name`.

4. **`platform_admins` es una tabla aparte.** El privilegio global sale de
   `profiles.role` y pasa a una tabla sin ninguna policy de escritura para
   `authenticated`. `profiles_hr_manage` lleva un `WITH CHECK` que prohíbe
   otorgar `SuperAdmin`, y un trigger congela `role` y `empresa_id` frente a
   auto-promoción.

## Consequences

**Positivas:**
- Las migraciones ahora se pueden aplicar en Supabase Cloud, que antes era
  imposible.
- Las policies de Storage siguen funcionando cuando se cree el bucket `cvs/`,
  porque `auth.role()` conserva su semántica nativa.
- El aislamiento de tenant deja de depender de datos que controla el cliente.
- Un HR comprometido no puede escalar más allá de su propio tenant.

**Negativas:**
- No hay auto-registro: alguien del tenant tiene que invitar. Para el
  career-site público esto no aplica (el candidato no crea cuenta), pero
  obliga a construir el flujo de invitación en el cockpit HRBP antes de que
  se pueda dar de alta al primer cliente.
- `JwtClaimsSchema` en `packages/types` cambia de forma: los claims pasan a
  `app_metadata` y `role` se llama `app_role`. Ya está actualizado, con un test
  de regresión que rechaza la forma antigua. `RunTokenClaimsSchema` **no**
  cambia: los run-tokens los emite Paperclip y los verifica hr-engine
  directamente (ADR-005), sin pasar por PostgREST, así que el claim `role`
  reservado no aplica ahí.
- Activar el hook en el dashboard de Supabase pasa de ser un paso recomendable
  a ser obligatorio: sin él, todas las policies de HR deniegan.

**Neutras:**
- Los tests de RLS cambiaron de forma: `assume_tenant` construye los claims
  anidados, y hay un `assume_anon` que usa el rol `anon` real en vez de
  `authenticated` sin claims. Esto último ocultaba los `revoke ... from anon`.

## Alternatives considered

| Alternativa | Por qué descartada |
|---|---|
| Mantener los helpers en `auth` y solo renombrar `auth.role()` | No resuelve el problema de ownership: cualquier función propia en un schema gestionado por la plataforma puede desaparecer en un upgrade. |
| Validar el metadata del signup contra una allowlist de dominios de email | `empresas.blacklist_dominios` ya existe y no se usa. Es más débil que una invitación: un dominio corporativo compartido deja entrar a cualquiera con esa dirección. Puede añadirse como capa extra, no como única. |
| Dejar `SuperAdmin` en `profiles` y filtrar por una allowlist de `empresa_id` | Sigue permitiendo que HR de un tenant lo otorgue; el filtro estaría en el mismo lugar que el atacante puede escribir. |
| Resolver el rol con un `SELECT` a `profiles` en cada policy en vez de leerlo del JWT | Un round-trip por fila evaluada. ADR-004 ya asumía 5-10% de overhead por RLS; esto lo multiplicaría. |
