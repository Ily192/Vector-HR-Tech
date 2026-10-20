# ADR-020: Toda la plataforma en un VPS, con Supabase autoalojado y Docker Compose

- **Status:** Accepted
- **Date:** 2026-10-20
- **Decider:** Ilyra ("pagando por separado varias instancias para un proyecto no es ni ordenado ni factible para el mantenimiento; si subimos la plataforma en un VPS y la gestionamos en un solo lado es más óptimo"). Delegó la decisión técnica: "piensa como un PM y un dev senior para tomar las mejores decisiones a largo plazo".
- **Supersedes:** ADR-010 (frontends en Vercel) y ADR-012 (backends en Fly.io), para el MVP
- **Tags:** infra, hosting, seguridad, costos, mantenimiento

## Context

**El despliegue gestionado necesitaba seis proveedores** para un solo producto: Supabase Cloud, Vercel, Fly.io, Upstash, Resend y Cloudflare. Cada uno trae su cuenta, sus secretos, su factura y su panel. Para un equipo de una persona, esa dispersión es un costo de mantenimiento en sí misma.

**Costaba unos US$57–64 al mes** antes del primer cliente, con precios del 2026-10-20:
- Supabase Pro: US$25.
- Vercel Pro: US$20. Hobby no permite uso comercial.
- Fly.io, el worker y el beat: US$7–9.
- Upstash: US$5–10, porque Celery consulta la cola sin parar.

**Qué es Supabase para esta app:** un conjunto de servicios de código abierto alrededor de Postgres.
- La lógica de datos ya es SQL puro: tablas, RLS, funciones y triggers viven en las migraciones `0001`–`0013`.
- GoTrue da los enlaces mágicos, las invitaciones y el hook del JWT.
- PostgREST da la API con la que el panel y el career site consultan bajo RLS.
- Storage guarda los CVs y firma sus URLs.
- El entorno local ya corre esos mismos servicios en Docker (Supabase CLI), y el MVP se probó de punta a punta contra él.

**Quitar Supabase y quedarse con Postgres solo** no simplifica el SQL, porque ya es SQL. Obligaría a reescribir Auth, la API y el almacenamiento de archivos: código de seguridad que hoy está probado y que habría que mantener para siempre.

## Decision

1. **Un VPS con todo.** Ubuntu LTS, 4 vCPU y al menos 8 GB de RAM (lo que Supabase recomienda para producción autoalojada).
   - Corre con **Docker Compose versionado en el repo** (`infra/vps/`) y con versiones de imagen fijas.
   - **Supabase autoalojado**, solo lo que se usa: `db`, `auth`, `rest`, `storage`, `kong`, `meta` y `studio`. Sin Realtime, Edge Functions ni analítica.
   - **hr-engine**: `api`, `worker` y un solo `beat`, más **Redis**.
   - **El career site** (Next.js en modo `standalone`) y **el panel** (archivos estáticos).
   - Delante de todo, **Caddy** con TLS.
2. **Se conserva Supabase y no se reescribe a SQL puro.** El código no cambia. Solo cambia la configuración: Supabase autoalojado usa las claves JWT legadas `anon` y `service_role`, que el código ya acepta.
3. **Fuera del VPS queda solo lo que no puede vivir bien ahí:**
   - **Resend** para el correo: la IP de un VPS cae en spam.
   - **Cloudflare** para el DNS, el proxy con WAF delante del VPS y Turnstile.
   - **Un bucket fuera del servidor** (Cloudflare R2) para los respaldos cifrados. Si el VPS se pierde, sus respaldos locales se pierden con él.
4. **Despliegue con un solo camino:** GitHub Actions construye las imágenes, las sube a GHCR y despliega por SSH (`docker compose pull` y `up -d`).
5. **Postgres nunca se expone a internet.** pgAdmin o DBeaver entran por un túnel SSH, y Studio, también por el túnel.
6. **La línea base de seguridad de abajo es parte de la decisión**, no un extra.

### Línea base de seguridad

- **Acceso:**
  - SSH solo con llave, sin `root` y con un usuario propio.
  - `ufw`: 443 y 80 solo desde las IPs de Cloudflare; SSH limitado.
  - `fail2ban`.
- **Parches:**
  - `unattended-upgrades` para el sistema.
  - Las imágenes de Docker se actualizan por PR, con versiones fijas, en una ventana mensual.
- **Secretos:**
  - Se regeneran **todos** los de la plantilla de Supabase autoalojado: el secreto del JWT, las claves `anon` y `service_role`, la contraseña de Postgres y la del panel. La plantilla oficial trae valores de demostración.
  - El `.env` vive en el servidor con permisos `600` y nunca entra al repo.
- **Datos:**
  - Postgres solo en la red interna de Docker.
  - La RLS no cambia.
  - El rol dueño solo lo usan las migraciones y el worker.
- **Respaldos:**
  - Cada noche, el volcado de Postgres y los archivos de Storage, cifrados, a R2.
  - Se guardan 7 diarios y 4 semanales.
  - Se prueba la restauración antes de recibir datos reales y después cada mes.
- **Vigilancia:**
  - Monitoreo externo con alertas para el career site, el panel y el `/ready` del hr-engine.
  - Alerta de disco.
  - Rotación de logs de Docker.

### Objetivos de recuperación

- **RPO de 24 horas** con el volcado diario. Se puede bajar a minutos con archivado de WAL cuando haya clientes que lo pidan.
- **RTO de menos de 4 horas:** levantar un VPS nuevo con el compose del repo y restaurar el último respaldo.

## Consequences

**Positivas:**
- **Un solo lado:** el repo y un servidor. Una factura principal y un mismo camino de despliegue.
- **Costo:** el VPS más Resend, Cloudflare y R2 en sus planes gratuitos, contra unos US$60 al mes del esquema gestionado. El rango depende del proveedor; ver la tabla de abajo.
- **Sin dependencia de proveedor:** todo es código abierto y el esquema es SQL puro. Volver a Supabase Cloud, o a un Postgres gestionado, es un `pg_dump` y un cambio de variables.
- **El mismo stack en desarrollo y en producción:** Supabase en Docker en los dos lados.

**Negativas:**
- **El equipo de operación es Ilyra, con Claude.** Unas 2–4 horas al mes de parches, respaldos y revisiones, que hay que agendar.
- **Un único punto de falla.** Se acepta mientras no haya un SLA con clientes. Se mitiga con respaldos fuera del servidor y una restauración probada.
- **Se pierden comodidades de los servicios gestionados:**
  - las vistas previas por PR de Vercel (más adelante, un compose de staging en el mismo VPS);
  - los respaldos y el PITR gestionados de Supabase;
  - sus actualizaciones automáticas;
  - las claves nuevas `sb_publishable_`/`sb_secret_`.

**Neutras:**
- `services/hr-engine/fly.toml` y `deploy-hr-engine.yml` (PR #75) se retiran cuando el stack del VPS los reemplace.
- ADR-007 (pgvector) sigue vigente: el Postgres de Supabase lo trae.
- Los proyectos de Vercel siguen sirviendo la demo hasta que el VPS esté en línea.

## Cuándo se revisa

Cualquiera de estas cosas:
- el primer cliente con un compromiso de disponibilidad (SLA);
- la base pasa de ~50 GB, o el CPU se sostiene arriba del 60 %;
- llega una segunda persona al equipo;
- la evaluación con IA del plan de pago pide más workers.

El primer paso sería separar Postgres en su propio servidor o en un servicio gestionado. Con el mismo esquema es un `pg_dump` y un `pg_restore`.

## Proveedor

La decisión no depende del proveedor: cualquier VPS con Ubuntu y Docker sirve. Precios consultados el 2026-10-20, a confirmar al contratar:

| Opción | Qué da | Precio |
|---|---|---|
| Hostinger KVM 4 (Phoenix o Boston) | 4 vCPU, 16 GB de RAM y 200 GB NVMe. Respaldo semanal del proveedor, que no reemplaza al nuestro fuera del servidor | US$12.99 al mes con plazo de 24 meses; renueva a US$28.99 |
| Vultr, 8 GB y 4 vCPU | Facturación mensual; región en Ciudad de México | ~US$40–48 al mes |
| Hetzner | Lo más barato en Europa | Subió en 2026; en EE. UU. solo la línea CPX, desde ~US$20 |

## Alternatives considered

| Alternativa | Por qué descartada |
|---|---|
| Seguir con los servicios gestionados | Seis proveedores para un producto y unos US$60 al mes antes del primer cliente. Es lo que Ilyra quiere evitar. |
| VPS con Postgres solo ("SQL puro") | Reescribir Auth (enlaces mágicos, invitaciones, sesiones), la API con RLS y el almacenamiento de CVs. Son semanas de código de seguridad nuevo, y más mantenimiento a largo plazo, no menos. El SQL ya es puro. |
| Coolify en el VPS | Otro sistema que actualizar y proteger, con su propio panel expuesto. El compose del repo se prueba igual en local y en producción. Se puede añadir después si hace falta una interfaz. |
| Supabase Cloud más un VPS para los workers | Ahorra unos US$10 al mes y deja la dispersión igual. |
