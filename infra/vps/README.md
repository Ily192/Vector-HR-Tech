# infra/vps

El backend de producción en un VPS de Contabo, con Docker Compose (ADR-020). El career
site (`empleos.`) y el panel (`panel.`) están en Vercel desde la enmienda del 2026-11-11;
aquí queda lo que hay detrás de `api.`. El runbook, del primer despliegue a la
recuperación, es `docs/runbooks/vps.md`.

| Ruta | Qué es |
|---|---|
| `compose.yml` | El stack: Supabase autoalojado (solo lo que se usa), hr-engine, Redis, Caddy y Cloudflare Tunnel |
| `.env.example` | La plantilla del `.env` del servidor (`/opt/vortex/.env`) |
| `caddy/` | El `Caddyfile` (solo la API) y la imagen de Caddy con las plantillas de correo de Auth |
| `supabase/` | El gateway (Envoy) y los SQL de arranque del Supabase autoalojado oficial, vendorizados; `db/vortex.sql` es propio |
| `scripts/` | Provisionar el servidor, generar secretos, desplegar, migrar, respaldar y restaurar |
| `systemd/` | El timer del respaldo nocturno |
| `pruebas/` | La prueba local de punta a punta (`pruebas/probar_en_local.sh`), con el career site y el panel levantados junto al stack solo para el e2e |

Antes de llevar un cambio al servidor se corre la prueba local (con Docker en marcha, y
pnpm y uv; en Windows, `PYTHON=python`):

```bash
infra/vps/pruebas/probar_en_local.sh
```

Levanta el stack con imágenes construidas en local, y le suma el career site y el panel
(que en producción están en Vercel) para que el e2e tenga el flujo completo. Los sitios
quedan en `localhost:8080` (career site), `:8081` (panel) y `:8082` (API). Contra eso
corre:

- el e2e del plan gratis, en modo despliegue (`E2E_REMOTO=1 pnpm e2e:flujo`): invitación,
  vacante, aplicaciones con CV, el worker del stack, el gancho, el .zip y eliminar;
- `humo.py`: el borde (Studio no se publica, 401 sin apikey, sin alta sin invitación) y las
  plantillas de correo en Mailpit;
- un respaldo a un S3 local, el borrado de la base y los CVs, la restauración, la
  comparación con lo de antes y el e2e otra vez.

Al final lo baja todo, volúmenes incluidos.
