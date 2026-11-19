# @fluveai/e2e

Dos suites de Playwright:

| Suite | Qué cubre | Contra qué | Comando |
|---|---|---|---|
| **smoke** (`tests/`) | El career site para candidatos: inicio, búsqueda, filtros, detalle y 404 | Los datos de ejemplo, o un `BASE_URL` | `pnpm e2e:smoke` |
| **flujo** (`flujo/`) | El plan gratis de punta a punta: alta e invitación, publicar con skills, 7 aplicaciones con CV, el worker, el gancho, el .zip, las etapas a mano (mover, contratar y descartar con motivo, ADR-024) y eliminar la vacante. Contra el stack del VPS, además el alta desde la web y la revisión humana desde `/admin` | El Supabase local, o un despliegue | `pnpm e2e:flujo` |

El flujo no corre en la CI: necesita Docker con Supabase y el hr-engine.

## El flujo en local

Hace falta:
- Docker Desktop y `pnpm db:start`.
- El hr-engine con sus dependencias (`python -m uv sync` en `services/hr-engine`).
- Chromium de Playwright (`pnpm --filter @fluveai/e2e e2e:install`).

```bash
pnpm db:start
pnpm e2e:flujo
```

Cómo funciona:
- **Servidores.** Levanta el career site (:3000) y el panel (:3001) con `pnpm dev`, apuntando al Supabase local. Si ya están corriendo, usa esos, y tienen que apuntar al Supabase local (`.env.local`).
- **Claves.** Las URLs y las claves salen de `supabase status`: ninguna está en el repo.
- **Alta e invitación.** El alta es el mismo comando que usa Vector HR (`python -m app.cli.alta_empresa`), y la invitación se lee en Mailpit.
- **Worker.** El barrido es la tarea que lanza Celery beat cada minuto, llamada una vez.
- **Python.** `E2E_PYTHON` cambia el Python que corre `-m uv` (por defecto, `python`).
- **Datos.** Cada corrida crea una empresa nueva, con una marca en el nombre que aparece en las anotaciones del reporte, y elimina su vacante al final.
- **Reporte.** Queda en `playwright-report/flujo`.

## La revisión humana desde `/admin` (ADR-022, 2026-11-17)

`flujo/revision-humana.spec.ts`: una empresa con correo de Gmail se registra desde la web
y publica; su primera vacante queda en revisión y fuera del career site. El admin abre
`panel/admin`, entra con su código y la aprueba, y sale en el career site. Otra vacante
que manda a WhatsApp, el admin la rechaza con un motivo y la empresa lo ve en
"Mis vacantes". Las métricas de la web (otro repo) se cortan con `route`: el tablero
avisa que no cargaron.

Necesita el hr-engine como API, Mailpit y el beat del stack, así que corre solo contra el
stack del VPS levantado en local, como `alta-con-codigo.spec.ts`; contra `pnpm db:start`
se salta. `infra/vps/pruebas/probar_en_local.sh` lo corre solo:

- `compose.local.yml` pone `ADMIN_CORREOS=admin@vortex.test` en el hr-engine y construye
  el panel con `VITE_ADMIN_API_URL` en su propio origen: `pruebas/Caddyfile` le pasa
  `/admin/*` al hr-engine, porque en modo producción el hr-engine no acepta localhost en
  `CORS_ALLOW_ORIGINS`;
- da de alta esa cuenta con `app.cli.alta_empresa`;
- y pasa `E2E_ADMIN_CORREO=admin@vortex.test`, además de `E2E_ALTA_URL`,
  `E2E_ALTA_SECRETO` y `E2E_MAILPIT_URL`.

Con el stack ya arriba (`VORTEX_CONSERVAR=1 infra/vps/pruebas/probar_en_local.sh`), solo
este spec:

```bash
E2E_REMOTO=1 E2E_CORREO=<la cuenta del alta> \
E2E_CAREER_SITE_URL=http://localhost:8080 E2E_PANEL_URL=http://localhost:8081 \
E2E_SUPABASE_URL=http://localhost:8082 E2E_SUPABASE_PUBLISHABLE_KEY=<ANON_KEY> \
E2E_SUPABASE_SECRET_KEY=<SERVICE_ROLE_KEY> \
E2E_ALTA_URL=http://localhost:8082/alta/plan-gratis E2E_ALTA_SECRETO=<ALTA_SECRETO> \
E2E_MAILPIT_URL=http://localhost:8025 E2E_ADMIN_CORREO=admin@vortex.test \
pnpm --filter @fluveai/e2e e2e:flujo flujo/revision-humana.spec.ts
```

Las claves salen del `.env` de prueba, cuya ruta imprime el script al terminar; ninguna va
en un archivo del repo. Espera
hasta 3 minutos por cada barrido de la moderación (uno por minuto).

## Contra un despliegue (el humo final)

```bash
E2E_REMOTO=1 \
E2E_CAREER_SITE_URL=https://… E2E_PANEL_URL=https://… \
E2E_SUPABASE_URL=https://… E2E_SUPABASE_PUBLISHABLE_KEY=… E2E_SUPABASE_SECRET_KEY=… \
E2E_CORREO=… pnpm e2e:flujo
```

- **`E2E_CORREO`.** Es la cuenta del panel de una empresa de prueba con plan gratis. Se da de alta una sola vez, con el comando de alta en el servidor.
- **Entrada.** Entra con un enlace de `generate_link` firmado con la clave secreta, sin correo: en producción los correos salen por Resend y no se pueden leer.
- **Worker.** Lo corre el servidor cada minuto, y el test espera hasta 4 minutos a que aparezca el gancho.
- **Cuota.** Cada corrida gasta una de las publicaciones de 30 días de esa empresa, porque eliminar la vacante no la devuelve.
- **Clave secreta.** Va solo en la variable de esa corrida, nunca en un archivo.
- **En el VPS (ADR-020)** las claves son las legadas del `.env` del servidor:
  - `E2E_SUPABASE_PUBLISHABLE_KEY` es `ANON_KEY`;
  - `E2E_SUPABASE_SECRET_KEY` es `SERVICE_ROLE_KEY`;
  - las dos van en `apikey` y como Bearer.
- **Estado.**
  - Se corrió el 2026-10-20 contra el stack del VPS levantado en local:
    `infra/vps/pruebas/probar_en_local.sh` lo corre antes y después de restaurar un
    respaldo.
  - Falta correrlo contra el VPS real cuando esté en línea.
