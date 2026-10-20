# @vortex/e2e

Dos suites de Playwright:

| Suite | Qué cubre | Contra qué | Comando |
|---|---|---|---|
| **smoke** (`tests/`) | El career site para candidatos: inicio, búsqueda, filtros, detalle y 404 | Los datos de ejemplo, o un `BASE_URL` | `pnpm e2e:smoke` |
| **flujo** (`flujo/`) | El plan gratis de punta a punta: alta e invitación, publicar con skills, 7 aplicaciones con CV, el worker, el gancho, el .zip y eliminar la vacante | El Supabase local, o un despliegue | `pnpm e2e:flujo` |

El flujo no corre en la CI: necesita Docker con Supabase y el hr-engine.

## El flujo en local

Hace falta:
- Docker Desktop y `pnpm db:start`.
- El hr-engine con sus dependencias (`python -m uv sync` en `services/hr-engine`).
- Chromium de Playwright (`pnpm --filter @vortex/e2e e2e:install`).

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
- **Estado.** Todavía no se ha corrido contra un despliegue; se prueba cuando el VPS esté en línea (ADR-020).
