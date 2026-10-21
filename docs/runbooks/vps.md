# Runbook · VPS en DigitalOcean

Toda la plataforma en un solo servidor (ADR-020): Supabase autoalojado, el hr-engine, el
career site, el panel y el diagnóstico gratuito de vectorhrtech.com, con Docker Compose. El stack vive en `infra/vps/` y se prueba
entero en local antes de llevar un cambio al servidor (`infra/vps/pruebas/probar_en_local.sh`).

Costo con precios del 2026-10-20: el droplet de 4 GB cuesta US$24 al mes, el respaldo
semanal de DigitalOcean US$4.80, y dos chequeos de disponibilidad US$2 (el primero es
gratis). Cloudflare (DNS, túnel, Turnstile y R2) y Resend quedan en sus planes gratis
mientras el volumen sea el del MVP. Total: unos US$31 al mes.

## Qué corre en el servidor

| Servicio | Qué es | Sale a internet |
|---|---|---|
| `db` | Postgres 17 de Supabase | no |
| `auth` | GoTrue: invitaciones, enlace mágico, hook del JWT | solo al SMTP de Resend |
| `rest` | PostgREST | no |
| `storage` | Storage de Supabase; los CVs en el volumen `storage` | no |
| `api-gw` | Envoy, el gateway del Supabase autoalojado: valida la apikey | no |
| `redis` | Cola de Celery, con contraseña | no |
| `hr-engine-api`, `hr-engine-worker`, `hr-engine-beat` | FastAPI, el worker y **un solo** beat | sí (proveedores de IA, Sentry, Turnstile y el SMTP de Resend para el aviso de los diagnósticos) |
| `career-site` | Next.js en modo `standalone` | sí (Turnstile) |
| `caddy` | Sirve el panel y el diagnóstico (estáticos) y reparte por dominio | no |
| `cloudflared` | Cloudflare Tunnel: la única entrada desde internet | sí |

- **No se publica ningún puerto en el host.** El túnel sale hacia Cloudflare. El Cloud
  Firewall de DigitalOcean solo deja entrar SSH.
- **Docker se salta `ufw`** para los puertos que publica un contenedor
  ([docs de Docker](https://docs.docker.com/engine/install/ubuntu/#firewall-limitations)).
  Por eso la barrera es el firewall de DigitalOcean, que vive fuera del servidor, y no
  `ufw`, que aquí solo cubre el SSH del host.
- **Redes de Docker:** `datos` y `borde` son internas (sin salida a internet). Solo
  `salida` la tiene, y solo la usa quien la necesita.
- **Perfil `admin` (bajo demanda):** Studio, postgres-meta y `tunel-db`. Escuchan en
  127.0.0.1 y se entra por túnel SSH.
- **Studio no pasa por el gateway ni por Caddy:** desde internet, `/`, `/pg/` y lo demás
  dan 404.

Por dominio (los cuatro en el `.env` y en las variables de GitHub):

| Dominio | Qué sirve Caddy |
|---|---|
| `DOMINIO_EMPLEOS` | El career site |
| `DOMINIO_PANEL` | El panel de la empresa |
| `DOMINIO_API` | Solo `/auth/v1`, `/rest/v1`, `/storage/v1` y `/salud/hr-engine` (para el monitoreo) |
| `DOMINIO_DIAGNOSTICO` | El diagnóstico gratuito (estático) y su único endpoint, `POST /api/diagnostico`, que Caddy reenvía a la RPC `registrar_diagnostico` (migración 0017) con la clave pública |

**El diagnóstico gratuito** (p. ej. `diagnostico.vectorhrtech.com`):

- El navegador solo habla con su propio dominio y con Turnstile: no conoce la URL de la
  API ni la clave pública, y su CSP no le deja conectar con nada más.
- Cada diagnóstico queda en `privado.diagnosticos`, que nadie puede leer por la API. Se
  ven en Studio (perfil `admin`).
- La base frena 3 por correo y 5 por IP en una hora, y 300 en 24 horas (responde 429).
  Encima va la regla del WAF de Cloudflare (paso 5, Cloudflare).
- El hr-engine (`diagnosticos.avisar`, cada minuto) verifica el token de Turnstile, que
  dura 300 s, descarta los que no pasan y manda **un** correo de resumen a
  `AVISO_DIAGNOSTICOS_PARA` (por omisión `hola@vectorhrtech.com`) por el mismo Resend que
  Auth. Resend gratis da 100 correos al día para los dos, así que el detalle llega hasta
  `AVISO_DIAGNOSTICOS_MAX_DIA` diagnósticos al día (20 por omisión) y los demás van en
  una línea: "y N diagnósticos más (revísalos en la base)".
- Sin `SMTP_PASS` no se avisa, y sin `TURNSTILE_SECRET_KEY` no se verifica; los dos
  quedan en `vortex logs hr-engine-worker` en cada barrido. Si un correo falla, se
  reintenta cada minuto hasta 5 veces; después el diagnóstico sigue en la base sin avisar.

## Antes de empezar

Cuentas, todas con 2FA. Las crea Ilyra: Claude no crea cuentas ni escribe credenciales.

- **DigitalOcean:** el servidor.
- **Cloudflare:** el dominio, el túnel (Zero Trust, plan Free), Turnstile y R2.
- **Resend:** el correo, con el dominio verificado.
- **GitHub:** el repo ya existe; solo faltan sus variables y secrets.

Dos llaves SSH en la máquina de Ilyra:

| Llave | Para qué | Contraseña |
|---|---|---|
| `C:\Users\ilyra\.ssh\digitalocean_ed25519` | Entrar al servidor como administradora | Sí, la pone Ilyra con `ssh-keygen -p -f <llave>` |
| `C:\Users\ilyra\.ssh\vortex_despliegue` | GitHub Actions; en el servidor solo puede correr `vortex-desplegar` | No: la usa la CI |

La de despliegue se crea así:

```bash
ssh-keygen -t ed25519 -N "" -C "github-actions-despliegue" -f ~/.ssh/vortex_despliegue
```

## Primer despliegue

### 1. DigitalOcean: cuenta y llave

- Settings → Security → **Add SSH Key**, con el contenido de `digitalocean_ed25519.pub`.
- Crear el proyecto **Vortex**. Los demás proyectos de Ilyra van en otro droplet
  (ADR-020): este servidor guarda CVs y no comparte máquina.

### 2. Crear el droplet

Create → Droplets:

| Opción | Valor |
|---|---|
| Región | **Atlanta (ATL1)**; si el plan no aparece ahí, Nueva York (NYC3). No hay región en Latinoamérica |
| Imagen | **Ubuntu 26.04 (LTS) x64**; si no aparece, 24.04 LTS. Docker soporta las dos |
| Plan | **Basic → Regular → 4 GB / 2 vCPU / 80 GB SSD** (US$24 al mes) |
| Autenticación | **SSH Key**: la de arriba. Nunca contraseña |
| Backups | **Weekly** (+20 %). Es una segunda capa: el respaldo propio va a R2 |
| Monitoring | **Improved Metrics and monitoring (Free)**: instala el agente |
| Hostname | `vortex-prod` |
| Tags | `vortex` |

Anotar la IP pública.

### 3. Cloud Firewall

Networking → Firewalls → **Create Firewall**, con el nombre `vortex`:

- **Inbound:** solo **SSH, TCP 22**. Si la IP de casa es fija, limitarlo a ella.
- **Outbound:** todo, como viene. El túnel sale por el puerto 7844 y el correo por el 2587.
- **Apply to:** el tag `vortex`.

Es gratis ([docs](https://docs.digitalocean.com/products/networking/firewalls/details/pricing/)).

### 4. Provisionar

Desde la raíz del repo, en la máquina de Ilyra:

```bash
scp -i ~/.ssh/digitalocean_ed25519 infra/vps/scripts/provisionar.sh root@<ip>:/root/
ssh -i ~/.ssh/digitalocean_ed25519 root@<ip> \
  bash /root/provisionar.sh ilyra "$(cat ~/.ssh/vortex_despliegue.pub)"
```

`provisionar.sh` deja el servidor así:

- **Usuarios:**
  - `ilyra` con sudo, y la misma llave que root.
  - `despliegue`, cuya llave solo puede correr `vortex-desplegar`.
- **SSH:** solo con llave, sin root.
- **Seguridad:** parches automáticos (reinicia a las 3 a. m. de Ciudad de México si un
  parche lo pide), fail2ban y `ufw` con solo SSH.
- **Sistema:** 2 GB de swap, hora en UTC, el agente de monitoreo, y Docker del
  repositorio oficial con rotación de logs.
- **Vortex:**
  - el repo en `/opt/vortex/repo`;
  - el comando `vortex` (docker compose con el `.env` y la versión);
  - el `.env` con los secretos generados;
  - el respaldo nocturno.

Se puede volver a correr sin riesgo. **Antes de cerrar esa sesión**, en otra terminal:
`ssh -i ~/.ssh/digitalocean_ed25519 ilyra@<ip>` (root ya no entra).

Para la consola de emergencia de DigitalOcean (Recovery Console), que sí pide contraseña:
`sudo passwd ilyra`. El SSH sigue sin aceptar contraseñas.

### 5. Cloudflare

1. **DNS:** el dominio en Cloudflare, con los registros de Vercel mientras tanto.
2. **Túnel:**
   - Zero Trust → Networking → Tunnels → **Create a tunnel** (Cloudflared), nombre
     `vortex`.
   - Elegir **Docker** y copiar solo el token del comando: va en
     `CLOUDFLARE_TUNNEL_TOKEN`. No hay que correr el comando; lo hace compose.
   - En **Routes → Add route → Published application**, cuatro rutas, todas con Service
     URL `http://caddy:80`: el subdominio del career site, el del panel, el de la API y el
     del diagnóstico (`diagnostico.vectorhrtech.com → http://caddy:80`).
   - En DNS, cada uno tiene que quedar como CNAME a `<id>.cfargotunnel.com`, con la nube
     naranja (Proxied). Si no apareció solo, se crea a mano.
   ([docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/get-started/create-remote-tunnel/))
3. **SSL/TLS:** activar *Always Use HTTPS*.
4. **Turnstile:** un widget con los hostnames del career site y del diagnóstico. La
   *site key* (pública) va en la variable de GitHub `TURNSTILE_SITE_KEY` y la *secret key*
   en `TURNSTILE_SECRET_KEY`; las dos sirven a los dos sitios.
5. **WAF, rate limiting del diagnóstico:** Security → WAF → **Rate limiting rules** →
   *Create rule*, nombre `diagnostico`:
   - *If incoming requests match:* `(http.host eq "diagnostico.vectorhrtech.com" and
     http.request.uri.path eq "/api/diagnostico")`;
   - *With the same characteristics:* IP;
   - *When rate exceeds:* 3 peticiones en 10 segundos;
   - *Then take action:* Block, por 10 segundos.

   El plan Free solo deja una regla, con ventana y bloqueo de 10 s
   ([docs](https://developers.cloudflare.com/waf/rate-limiting-rules/)). Corta las ráfagas
   antes de que lleguen al servidor; los frenos por hora y por día están en la base.
6. **R2:**
   - Un bucket `vortex-respaldos`, sin acceso público.
   - *Manage API tokens* → un token con **Object Read & Write solo sobre ese bucket**. Da
     un *Access Key ID* y un *Secret Access Key* (`R2_ACCESS_KEY_ID` y
     `R2_SECRET_ACCESS_KEY`).
   - El endpoint va en `RESTIC_REPOSITORY`:
     `s3:https://<ACCOUNT_ID>.r2.cloudflarestorage.com/vortex-respaldos`.

### 6. Resend

- Domains → añadir el dominio y poner en Cloudflare los registros que pide (SPF y DKIM).
- API Keys → una con *Sending access* solo para ese dominio: va en `SMTP_PASS`.
- **El puerto es 2587** (STARTTLS). DigitalOcean bloquea 25, 465 y 587 en todos los
  droplets ([docs](https://docs.digitalocean.com/support/why-is-smtp-blocked/)), y Resend
  acepta 2587 ([docs](https://resend.com/docs/send-with-smtp)).

### 7. El `.env` del servidor y GitHub

1. **Llenar lo que falta:** `sudo nano /opt/vortex/.env`. Lo que va a mano:
   - los cuatro `DOMINIO_*`;
   - `SMTP_PASS` y `SMTP_ADMIN_EMAIL` (un remitente del dominio verificado). El hr-engine
     los usa también para el aviso de los diagnósticos;
   - `CLOUDFLARE_TUNNEL_TOKEN` y `TURNSTILE_SECRET_KEY`;
   - si hace falta cambiarlos: `AVISO_DIAGNOSTICOS_PARA` (a quién llega el aviso, por
     omisión `hola@vectorhrtech.com`) y `AVISO_DIAGNOSTICOS_MAX_DIA` (20);
   - `RESTIC_REPOSITORY`, `R2_ACCESS_KEY_ID` y `R2_SECRET_ACCESS_KEY`;
   - `GOOGLE_API_KEY`, la key de Gemini del **nivel de pago**, para la evaluación con IA
     (ADR-021). Sin ella, las aplicaciones de las empresas con IA esperan;
   - opcional: `RESPALDO_PING_URL` y `OPENAI_API_KEY` (respaldo de Gemini).
2. **Comprobar:**
   `sudo -u despliegue python3 /opt/vortex/repo/infra/vps/scripts/generar_secretos.py --verificar /opt/vortex/.env`.
   No imprime nada si todo está.
3. **Guardar `RESTIC_PASSWORD` en el gestor de contraseñas**, junto con la llave de R2:
   `sudo grep ^RESTIC_PASSWORD= /opt/vortex/.env`. Sin eso no se restaura nada.
4. **GitHub → Settings → Secrets and variables → Actions → Variables:**
   - `DOMINIO_EMPLEOS`, `DOMINIO_PANEL`, `DOMINIO_API` y `DOMINIO_DIAGNOSTICO`: los
     mismos del `.env`.
   - `SUPABASE_ANON_KEY`: la salida de
     `sudo -u despliegue python3 /opt/vortex/repo/infra/vps/scripts/generar_secretos.py --clave-publica /opt/vortex/.env`.
     Es pública: va en el navegador.
   - `TURNSTILE_SITE_KEY`.
5. **GitHub → Settings → Environments → `production` → Secrets:**
   - `VPS_HOST`: la IP.
   - `VPS_SSH_KEY`: el contenido de `~/.ssh/vortex_despliegue`, la privada.
   - `VPS_KNOWN_HOSTS`: la salida de `ssh-keyscan -t ed25519 <ip>`. Antes, comparar la
     huella con la del servidor: `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`, dentro
     del servidor.

### 8. Desplegar

Actions → **Deploy VPS (DigitalOcean)** → *Run workflow* desde `main`.

- **Qué hace:**
  - construye y sube a GHCR las tres imágenes (`vortex-hr-engine`, `vortex-career-site` y
    `vortex-caddy`, etiquetadas con el commit);
  - entra por SSH y corre `scripts/levantar.sh`: la base, Auth y Storage, las migraciones
    que falten (`scripts/migrar.sh`) y el resto;
  - comprueba los cuatro dominios desde internet.
- **Seguridad:**
  - el servidor baja las imágenes con el `GITHUB_TOKEN` del job, que caduca al terminar;
  - en el servidor no queda ningún token de GitHub;
  - solo se despliega un commit que esté en `main`.

En el servidor: `vortex ps` muestra todo `healthy` (el beat no tiene healthcheck), y
`vortex logs -f --tail 50 hr-engine-beat` muestra un barrido por minuto.

### 9. Monitoreo

DigitalOcean → Monitoring:

- **Alert policies** (gratis), por correo:
  - CPU > 80 % por 10 min;
  - memoria > 85 % por 10 min;
  - disco > 80 % por 5 min.
- **Uptime:** tres chequeos con alertas de caída y de certificado. El primero es gratis
  y los demás cuestan US$1 al mes cada uno.
  - `https://<DOMINIO_PANEL>/`;
  - `https://<DOMINIO_EMPLEOS>/`;
  - `https://<DOMINIO_API>/salud/hr-engine` (responde `ok` si el hr-engine ve a Postgres y
    a Redis).
- **Opcional:** un chequeo de Healthchecks.io en `RESPALDO_PING_URL`. Avisa si una noche
  el respaldo no corrió.

### 10. Primer respaldo y prueba de restauración

**Antes de dar de alta a la primera empresa**, mientras no hay datos reales:

```bash
sudo systemctl start vortex-respaldo && journalctl -u vortex-respaldo -n 30
sudo -u despliegue /opt/vortex/repo/infra/vps/scripts/restaurar.sh latest --si
```

La restauración borra la base y los CVs y pone los del snapshot. Después, `vortex ps`
tiene que mostrar todo sano.

### 11. La primera empresa

```bash
vortex exec hr-engine-api python -m app.cli.alta_empresa \
  --empresa "Ferretería Norte" --correo ana@ferreterianorte.mx --nombre "Ana Ruiz" --tamano 35
```

`--reenviar <correo>` manda otro enlace a quien no ha entrado.

## Día a día

- **Desplegar:** el workflow, desde `main`.
- **Volver atrás:** el mismo workflow desde un commit anterior de `main`. Las imágenes
  siguen en GHCR. Las migraciones no se deshacen: van siempre hacia adelante y
  compatibles con la versión anterior (expand/contract, `deploy.md`).
- **Logs:** `vortex logs -f --tail 100 <servicio>`.
- **Studio:**
  1. En el servidor: `vortex --profile admin up -d studio`.
  2. En la máquina de Ilyra: `ssh -L 3000:127.0.0.1:3000 ilyra@<ip>` y abrir
     http://localhost:3000.
  3. Al terminar: `vortex --profile admin stop studio meta`. Ocupa ~0.5 GB.
- **pgAdmin o DBeaver:**
  1. `vortex --profile admin up -d tunel-db`.
  2. `ssh -L 5432:127.0.0.1:5432 ilyra@<ip>`.
  3. Conectarse a `localhost:5432` como `postgres`, con `POSTGRES_PASSWORD` del `.env`.
  4. Al terminar: `vortex --profile admin stop tunel-db`.

## Mantenimiento mensual (1 a 2 horas)

1. **Sistema:** `sudo apt update && sudo apt upgrade`.
   - Los parches de seguridad ya entran solos; esto trae lo demás, Docker incluido.
   - Si pide reinicio, `sudo reboot`: el stack vuelve solo.
2. **Respaldos:**
   - `journalctl -u vortex-respaldo --since "-7 days"`;
   - el snapshot más reciente: `vortex run --rm respaldo snapshots --latest 3`.
3. **Probar una restauración** en un droplet temporal. No en el de producción, que ya
   tiene datos:
   1. Crear un droplet como en el paso 2 (cuesta centavos por hora).
   2. Provisionar con `provisionar.sh`.
   3. Poner en el `/opt/vortex/.env` que dejó `provisionar.sh` los valores reales de
      `RESTIC_REPOSITORY`, `RESTIC_PASSWORD` y la llave de R2. El resto lo trae el snapshot.
   4. Restaurar: `sudo -u despliegue /opt/vortex/repo/infra/vps/scripts/restaurar.sh latest --si`.
      Se detiene en "falta desplegar".
   5. Comprobar los datos:
      ```bash
      vortex up -d db
      vortex exec db psql -U postgres -c "select count(*) from public.applications"
      ```
   6. Destruir el droplet.
4. **Disco y Docker:** `df -h`, `docker system df`, y
   `docker image prune -af --filter until=720h`, que borra imágenes de más de 30 días.
5. **Métricas:** revisar las de DigitalOcean. Si la memoria pasa del 75 % de forma
   sostenida, ver "Crecer".
6. **Versiones:** ver la sección siguiente.

## Actualizar versiones

Siempre por PR, nunca a mano en el servidor:

1. **Supabase:**
   - Mirar las imágenes que corre el CLI fijado en `package.json` (`supabase start`) y
     `docker/versions.md` de supabase/supabase.
   - Cambiar las etiquetas de `infra/vps/compose.yml`.
   - Regenerar el gateway y los SQL de arranque con el commit nuevo de supabase/supabase:
     `python3 infra/vps/scripts/vendorizar_supabase.py <commit>`, y revisar el diff.
2. **El resto** (Envoy, Redis, Caddy, cloudflared, restic, Node): la etiqueta en
   `compose.yml` o en los Dockerfiles de `infra/vps/`.
3. **Probar en local:** `infra/vps/pruebas/probar_en_local.sh`. Levanta el stack con
   imágenes locales y corre contra él:
   - el e2e del plan gratis (`E2E_REMOTO=1 pnpm e2e:flujo`, de `packages/e2e`);
   - las revisiones del borde (`humo.py`);
   - un respaldo, la restauración y el e2e otra vez.
4. **Llevarlo al servidor:** merge y desplegar. Después, el mismo e2e contra el servidor
   real (`packages/e2e/README.md`, "Contra un despliegue"), con una empresa de prueba.

## Crecer: de 4 a 8 GB

Cuando la memoria pasa del 75 % de forma sostenida, o con el primer cliente de pago:

1. En el servidor, `sudo poweroff`.
2. En DigitalOcean, Resize → **CPU and RAM only** → Basic 8 GB / 4 vCPU (US$48).
   - Se puede deshacer; el disco, no ([docs](https://docs.digitalocean.com/products/droplets/how-to/resize/)).
   - Corte de alrededor de un minuto por GB de disco usado.
3. Encender. El stack vuelve solo.
4. Subir por PR los `mem_limit` de `db` y `hr-engine-worker` en `compose.yml`.

## Rotar secretos

| Secreto | Cómo |
|---|---|
| `REDIS_PASSWORD`, `HR_ENGINE_JWT_SECRET`, `DASHBOARD_PASSWORD`, `PG_META_CRYPTO_KEY` | Vaciar su valor en el `.env`, correr `generar_secretos.py /opt/vortex/.env` y `vortex up -d` |
| `JWT_SECRET` | Lo mismo, y regenera `ANON_KEY` y `SERVICE_ROLE_KEY`. Hay que actualizar la variable `SUPABASE_ANON_KEY` de GitHub y volver a desplegar (el panel la lleva dentro). Cierra todas las sesiones |
| `POSTGRES_PASSWORD` | No basta con el `.env`: `roles.sql` solo corre al crear la base. Primero, en `vortex exec db psql -U supabase_admin`, `ALTER USER … WITH PASSWORD '<nueva>'` para `postgres`, `authenticator`, `pgbouncer`, `supabase_auth_admin`, `supabase_functions_admin` y `supabase_storage_admin`. Después, el `.env` y `vortex up -d` |
| `CLOUDFLARE_TUNNEL_TOKEN`, `SMTP_PASS`, `TURNSTILE_SECRET_KEY` y la llave de R2 | Rotarlos en su panel, cambiar el `.env` y `vortex up -d` |
| `RESTIC_PASSWORD` | `vortex run --rm respaldo key add`, después `key remove` de la vieja. Guardar la nueva en el gestor |
| La llave de despliegue | Una nueva con `ssh-keygen`, `provisionar.sh` con la pública y el secret `VPS_SSH_KEY` |

## Recuperar el servidor

Si el droplet se pierde (RTO menor de 4 horas, ADR-020):

1. **Droplet nuevo** como en los pasos 2 y 3, y provisionar como en el paso 4.
2. **Restaurar:**
   1. Poner en el `/opt/vortex/.env` que dejó `provisionar.sh` los valores reales de
      `RESTIC_REPOSITORY`, `RESTIC_PASSWORD`, `R2_ACCESS_KEY_ID` y `R2_SECRET_ACCESS_KEY`
      (del gestor de contraseñas).
   2. Correr `sudo -u despliegue /opt/vortex/repo/infra/vps/scripts/restaurar.sh latest --si`.
   3. Trae la base, los CVs y el `.env` completo del snapshot.
3. **GitHub:** actualizar `VPS_HOST` y `VPS_KNOWN_HOSTS` y correr el workflow.
4. **Cloudflare no cambia.** El `.env` restaurado trae el token del túnel, así que el
   servidor nuevo entra por el mismo túnel y los DNS no se tocan.

## Presupuesto de memoria

Medido en la prueba local (`probar_en_local.sh`), en reposo después de dos corridas del
e2e (14 aplicaciones con CV) y una restauración:

| Servicio | Tope (`mem_limit`) | Medido |
|---|---|---|
| `db` | 576 MB | 124 MB |
| `auth` | 96 MB | 14 MB |
| `rest` | 160 MB | 78 MB |
| `storage` | 192 MB | 80 MB |
| `api-gw` | 128 MB | 37 MB |
| `redis` | 80 MB | 7 MB |
| `hr-engine-api` | 192 MB | 102 MB |
| `hr-engine-worker` | 512 MB | 271 MB |
| `hr-engine-beat` | 224 MB | 134 MB |
| `career-site` | 256 MB | 54 MB |
| `caddy` | 64 MB | 16 MB |
| `cloudflared` | 96 MB | no corre en local |
| **Total** | **2.5 GB** | **~0.95 GB** |

En 4 GB, con ~0.45 GB del sistema:

- **Si todos llegaran a su tope a la vez:** queda ~1 GB libre, más 2 GB de swap.
- **Uso real:** ~1.4 GB.
- **Con el perfil `admin` encendido:** suma ~0.7 GB (Studio 512 MB, meta 128 MB y el
  túnel 32 MB). Por eso se apaga al terminar.

## Fuentes

- Supabase autoalojado:
  - [Self-Hosting with Docker](https://supabase.com/docs/guides/self-hosting/docker) (requisitos, secretos, proxy);
  - [Envoy como gateway por defecto](https://github.com/orgs/supabase/discussions/48048).
- [Docker Engine en Ubuntu](https://docs.docker.com/engine/install/ubuntu/) (versiones soportadas, repositorio, límites con el firewall).
- PostgreSQL 17: [`pg_basebackup`](https://www.postgresql.org/docs/17/app-pgbasebackup.html) (`-D - -F t -X fetch`).
- Respaldos:
  - restic: [repositorio S3](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html);
  - Cloudflare R2: [región `auto`](https://developers.cloudflare.com/r2/api/s3/api/).
- Cloudflare Tunnel:
  - [crear el túnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/get-started/create-remote-tunnel/);
  - [parámetros de `cloudflared tunnel run`](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/configure-tunnels/cloudflared-parameters/run-parameters/).
- DigitalOcean:
  - [precios de Droplets](https://www.digitalocean.com/pricing/droplets);
  - [resize](https://docs.digitalocean.com/products/droplets/how-to/resize/);
  - [Monitoring](https://docs.digitalocean.com/products/monitoring/details/pricing/);
  - [Uptime](https://docs.digitalocean.com/products/uptime/details/pricing/);
  - [agente de métricas](https://docs.digitalocean.com/products/monitoring/how-to/install-agent/);
  - [SMTP bloqueado](https://docs.digitalocean.com/support/why-is-smtp-blocked/).
- [GHCR: visibilidad y permisos](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility).
- Next.js 16 (`node_modules/next/dist/docs`):
  - `output`, "Automatically Copying Traced Files";
  - "Self-Hosting";
  - "Caching without Cache Components", `dynamic`.
