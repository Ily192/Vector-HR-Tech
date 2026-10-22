# ADR-020: Toda la plataforma en un VPS, con Supabase autoalojado y Docker Compose

- **Status:** Accepted
- **Date:** 2026-10-20
- **Decider:** Ilyra ("pagando por separado varias instancias para un proyecto no es ni ordenado ni factible para el mantenimiento; si subimos la plataforma en un VPS y la gestionamos en un solo lado es más óptimo"). Delegó la decisión técnica: "piensa como un PM y un dev senior para tomar las mejores decisiones a largo plazo".
- **Supersedes:** ADR-010 (frontends en Vercel) y ADR-012 (backends en Fly.io), para el MVP
- **Tags:** infra, hosting, seguridad, costos, mantenimiento

*Actualizado el 2026-10-20, con el stack ya construido (`infra/vps/`, runbook
`docs/runbooks/vps.md`).* Cambió:

- **Proveedor:** DigitalOcean (Ilyra: "vamos con digitalocean y separamos los servidores").
- **Tamaño:** se empieza con 4 GB, no con 8.
- **Entrada:** Cloudflare Tunnel en lugar de puertos abiertos.
- **Gateway:** Envoy en lugar de Kong.
- **Puerto del correo:** 2587.
- **Un error corregido:** la versión anterior confiaba en `ufw` para filtrar el 80 y el
  443, y eso no funciona con Docker (ver "Línea base de seguridad").

*Enmienda del 2026-10-22: el proveedor es Contabo.* Ilyra: "iba a ser digital ocean pero
compré contabo por más capacidad". Lo demás de este ADR sigue igual. Lo que cambia:

- **Firewall:** Contabo no pone un firewall de red delante del VPS, así que la barrera es
  `ufw` con solo SSH. Sirve porque ningún servicio publica puertos hacia afuera (Docker se
  salta `ufw` solo para los publicados); los del perfil `admin` van en 127.0.0.1.
- **Correo:** sigue en 2587. Contabo bloquea el 25 de salida.
- **Monitoreo:** sin el agente ni las alertas de DigitalOcean. Uptime con UptimeRobot
  (gratis) y revisión mensual de memoria y disco.
- **Respaldo del proveedor:** el Auto Backup de Contabo, opcional, en lugar del semanal de
  DigitalOcean. El respaldo propio a R2 no cambia.
- **Prueba de restauración:** en un servidor temporal por horas, porque Contabo cobra por
  mes.

Donde abajo dice DigitalOcean o droplet, léase el VPS de Contabo. El runbook ya está al día.

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

1. **Un VPS con todo, en DigitalOcean:**
   - **Droplet:** Basic Regular de **4 GB y 2 vCPU** (US$24 al mes), en Atlanta, con
     Ubuntu 26.04 LTS.
   - **Por qué 4 GB:** es el mínimo de Supabase autoalojado, y alcanza porque no se corre
     Realtime ni la analítica. Medido en local, el stack entero usa ~0.95 GB en reposo.
   - **Cuándo crecer:** a 8 GB y 4 vCPU (US$48) cuando la memoria pase del 75 % de forma
     sostenida, o con el primer cliente de pago. Es un *resize* de CPU y RAM, que se
     puede deshacer y corta unos minutos.
   - **Docker Compose versionado en el repo** (`infra/vps/`), con versiones de imagen
     fijas.
   - **Supabase autoalojado, solo lo que se usa:** `db`, `auth`, `rest`, `storage` y el
     gateway. `meta` y `studio` quedan en un perfil que se enciende para usarlo. Sin
     Realtime, Edge Functions, analítica ni pooler.
   - **Las imágenes de Supabase son las del CLI fijado en el repo (2.120.0):** el mismo
     Postgres, GoTrue, PostgREST y Storage del desarrollo local.
   - **El gateway es Envoy**, no Kong: es el que trae por defecto el Supabase autoalojado
     desde agosto de 2026, porque la versión libre de Kong dejó de avanzar
     ([supabase/discussions#48048](https://github.com/orgs/supabase/discussions/48048)).
     Su configuración se trae del repo oficial con `infra/vps/scripts/vendorizar_supabase.py`.
   - **hr-engine:** `api`, `worker` y un solo `beat`, más **Redis** con contraseña.
   - **El career site** (Next.js en modo `standalone`) y **el panel** (archivos estáticos,
     dentro de la imagen de Caddy).
   - **Caddy** reparte por dominio. Del dominio de la API solo publica `/auth/v1`,
     `/rest/v1` y `/storage/v1`, más `/salud/hr-engine` para el monitoreo.
2. **Se conserva Supabase y no se reescribe a SQL puro.** El código no cambia. Solo cambia la configuración: Supabase autoalojado usa las claves JWT legadas `anon` y `service_role`, que el código ya acepta.
3. **La única entrada desde internet es Cloudflare Tunnel.** `cloudflared` abre un túnel
   saliente y el servidor no publica ningún puerto. Cloudflare termina el TLS; dentro todo
   es HTTP.
4. **Fuera del VPS queda solo lo que no puede vivir bien ahí:**
   - **Resend** para el correo: la IP de un VPS cae en spam. Por SMTP en el puerto 2587,
     porque DigitalOcean bloquea el 25, el 465 y el 587 en todos los droplets.
   - **Cloudflare** para el DNS, el túnel, el WAF y Turnstile.
   - **Un bucket fuera del servidor** (Cloudflare R2) para los respaldos cifrados. Si el
     VPS se pierde, sus respaldos locales se pierden con él.
5. **Despliegue con un solo camino** (`deploy-vps.yml`):
   - GitHub Actions construye las imágenes y las sube a GHCR, etiquetadas con el commit.
   - Después entra por SSH con una llave que en el servidor solo puede correr el script de
     despliegue.
   - El servidor baja las imágenes con el `GITHUB_TOKEN` del job, que caduca al terminar:
     ahí no queda ningún token de GitHub.
   - Solo se despliegan commits que estén en `main`.
6. **Postgres nunca se expone a internet.** pgAdmin o DBeaver entran por un túnel SSH, y Studio, también por el túnel.
7. **La línea base de seguridad de abajo es parte de la decisión**, no un extra.
8. **Este servidor es solo de Vortex.** Los demás proyectos de Ilyra van en otro droplet,
   con su propia llave de despliegue:
   - aquí hay CVs, que son datos personales;
   - cada app extra es otra puerta a la misma máquina;
   - el acceso a Docker equivale a ser root.

### Línea base de seguridad

- **Red:**
  - Ningún puerto publicado hacia afuera. El tráfico web entra por el túnel.
  - **Cloud Firewall de DigitalOcean** (gratis): solo SSH de entrada. Vive fuera del
    servidor, así que Docker no lo puede saltar.
  - **Corrección:** la primera versión de esta ADR decía "`ufw`: 443 y 80 solo desde las
    IPs de Cloudflare". Era un error: los puertos que publica Docker se saltan las reglas
    de `ufw` ([docs de Docker](https://docs.docker.com/engine/install/ubuntu/#firewall-limitations)).
    `ufw` queda como segunda capa del host, con solo SSH.
  - **Redes de Docker:** la base, Redis, PostgREST y Storage están en una red interna sin
    salida a internet. Solo salen Auth (al SMTP), el career site (a Turnstile), el
    hr-engine, el túnel y el respaldo (a R2).
- **Acceso:**
  - SSH solo con llave, sin `root` y con un usuario propio.
  - La llave de despliegue solo puede correr `vortex-desplegar`, sin terminal ni reenvío
    de puertos.
  - `fail2ban`.
- **Parches:**
  - `unattended-upgrades` para el sistema, con reinicio a las 3 a. m. de Ciudad de México
    si un parche lo pide.
  - Las imágenes de Docker se actualizan por PR, con versiones fijas, en una ventana mensual.
- **Secretos:**
  - Se generan **todos** en el servidor (`generar_secretos.py`), sin mostrarse: el secreto
    del JWT, las claves `anon` y `service_role`, y las contraseñas de Postgres, Redis y el
    panel. La plantilla oficial trae valores de demostración.
  - El `.env` vive en el servidor con permisos `600` y nunca entra al repo.
  - Va cifrado en cada respaldo. Fuera del servidor se guardan solo `RESTIC_PASSWORD` y
    la llave de R2, en el gestor de contraseñas.
- **Datos:**
  - Postgres solo en la red interna de Docker.
  - La RLS no cambia.
  - El rol dueño solo lo usan las migraciones y el hr-engine.
  - Las cuentas nacen solo de una invitación: el trigger `handle_new_user` rechaza el
    alta sin ella. El registro de Auth queda encendido como en desarrollo, porque
    apagarlo niega el enlace mágico a quien fue invitado y todavía no entró (se vio
    en la prueba local).
- **Memoria:** cada servicio tiene su tope. El que se desborda muere solo y Docker lo
  reinicia, en vez de tumbar el servidor. Hay 2 GB de swap.
- **Respaldos:**
  - Cada noche, con restic a R2, cifrados en el servidor:
    - la copia física de la base (`pg_basebackup`), que es la que se restaura;
    - un volcado lógico (`pg_dump`);
    - los archivos de Storage;
    - la config de la base;
    - el `.env`.
  - Se guardan 7 diarios y 4 semanales.
  - Encima, el respaldo semanal de DigitalOcean del disco entero (+20 %).
  - Se prueba la restauración antes de recibir datos reales y después cada mes, en un
    droplet temporal.
- **Vigilancia:**
  - Alertas gratis de DigitalOcean: CPU, memoria y disco.
  - Chequeos de disponibilidad del career site, el panel y `/salud/hr-engine`.
  - Opcional, un aviso si una noche el respaldo no corrió.
  - Rotación de logs de Docker.

### Objetivos de recuperación

- **RPO de 24 horas** con el respaldo diario. Se puede bajar a minutos con archivado de
  WAL cuando haya clientes que lo pidan.
- **RTO de menos de 4 horas:**
  - levantar un droplet nuevo, provisionarlo, restaurar el último snapshot y desplegar;
  - Cloudflare no cambia: el servidor nuevo entra por el mismo túnel.
  - El procedimiento se probó en local con `infra/vps/pruebas/probar_en_local.sh`.

## Consequences

**Positivas:**
- **Un solo lado:** el repo y un servidor. Una factura principal y un mismo camino de despliegue.
- **Costo:** unos US$31 al mes contra unos US$60 del esquema gestionado:
  - el droplet, US$24;
  - el respaldo de DigitalOcean, US$4.80;
  - dos chequeos de disponibilidad, US$2;
  - Resend, Cloudflare y R2 en sus planes gratuitos.
- **Sin dependencia de proveedor:** todo es código abierto y el esquema es SQL puro. Volver a Supabase Cloud, o a un Postgres gestionado, es un `pg_dump` y un cambio de variables.
- **Casi el mismo stack en desarrollo y en producción:** las mismas imágenes de Supabase.

**Negativas:**
- **El equipo de operación es Ilyra, con Claude.** Unas 2–4 horas al mes de parches, respaldos y revisiones, que hay que agendar.
- **Un único punto de falla.** Se acepta mientras no haya un SLA con clientes. Se mitiga con respaldos fuera del servidor y una restauración probada.
- **Se pierden comodidades de los servicios gestionados:**
  - las vistas previas por PR de Vercel (más adelante, un compose de staging en el mismo VPS);
  - los respaldos y el PITR gestionados de Supabase;
  - sus actualizaciones automáticas;
  - las claves nuevas `sb_publishable_`/`sb_secret_`.
- **El gateway de producción no es el de desarrollo:** el CLI corre Kong 2.8.1 y aquí va
  Envoy. Cumplen el mismo contrato (rutas y validación de la apikey), y la prueba local del
  stack lo comprueba de punta a punta antes de cada cambio.
- **No hay región en Latinoamérica.** Con Cloudflare delante son decenas de milisegundos,
  que esta app no nota. El aviso de privacidad tiene que decir que los datos están en
  EE. UU. (revisión legal pendiente).

**Neutras:**
- Se retiraron `services/hr-engine/fly.toml` y `deploy-hr-engine.yml` (PR #75).
- ADR-007 (pgvector) sigue vigente: el Postgres de Supabase lo trae.
- Los proyectos de Vercel siguen sirviendo la demo hasta que el VPS esté en línea.

## Cuándo se revisa

Cualquiera de estas cosas:
- el primer cliente con un compromiso de disponibilidad (SLA);
- la base pasa de ~50 GB, o el CPU se sostiene arriba del 60 % ya con 8 GB;
- llega una segunda persona al equipo;
- la evaluación con IA del plan de pago pide más workers.

El primer paso sería separar Postgres en su propio servidor o en un servicio gestionado. Con el mismo esquema es un `pg_dump` y un `pg_restore`.

## Proveedor

**DigitalOcean**, con precios del 2026-10-20:

- **Por qué:**
  - Cobra por segundo, con tope mensual y sin contrato.
  - Crece en minutos.
  - Trae firewall de red, monitoreo y alertas gratis.
  - Tiene chequeos de disponibilidad y respaldo del disco completo.
- **En contra:**
  - Cuesta más por GB de RAM que Hostinger.
  - No tiene región en Latinoamérica.

| Opción | Qué da | Precio | Veredicto |
|---|---|---|---|
| **DigitalOcean, Basic 4 GB / 2 vCPU** | Facturación por segundo, firewall de red gratis, monitoreo, *resize* en minutos | US$24 al mes; 8 GB y 4 vCPU, US$48 | **Elegido** |
| Hostinger KVM 4 | 16 GB de RAM y 200 GB NVMe | US$12.99 al mes con plazo de 24 meses; renueva a US$28.99 | Más RAM por dólar, pero con contrato y menos herramientas de operación |
| Vultr, 8 GB y 4 vCPU | Lo mismo que DigitalOcean y región en Ciudad de México | ~US$40–48 al mes | Casi empate; la región no pesa con Cloudflare delante |
| Hetzner | Lo más barato en Europa | Subió en 2026; en EE. UU. solo la línea CPX, desde ~US$20 | Lejos de los usuarios |

## Alternatives considered

| Alternativa | Por qué descartada |
|---|---|
| Seguir con los servicios gestionados | Seis proveedores para un producto y unos US$60 al mes antes del primer cliente. Es lo que Ilyra quiere evitar. |
| VPS con Postgres solo ("SQL puro") | Reescribir Auth (enlaces mágicos, invitaciones, sesiones), la API con RLS y el almacenamiento de CVs. Son semanas de código de seguridad nuevo, y más mantenimiento a largo plazo, no menos. El SQL ya es puro. |
| Coolify en el VPS | Otro sistema que actualizar y proteger, con su propio panel expuesto. El compose del repo se prueba igual en local y en producción. Se puede añadir después si hace falta una interfaz. |
| Supabase Cloud más un VPS para los workers | Ahorra unos US$10 al mes y deja la dispersión igual. |
| Abrir el 80 y el 443 solo a las IPs de Cloudflare | Habría que mantener la lista de IPs en el firewall, y la IP del servidor sería alcanzable. Con el túnel no hay puertos que cuidar, y un servidor nuevo no requiere tocar el DNS. |
| Kong como gateway (el del CLI) | El CLI trae Kong 2.8, una versión vieja, y la versión libre de Kong 3 dejó de avanzar. Supabase pasó a Envoy para autoalojar. |
| Todos los proyectos de Ilyra en el mismo servidor | Más barato, pero cualquier proyecto con una dependencia vieja o un despliegue comprometido quedaría al lado de los CVs, y un pico de memoria de otro proyecto tumbaría Vortex. |
