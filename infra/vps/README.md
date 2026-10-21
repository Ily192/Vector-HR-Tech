# infra/vps

Producción en un solo VPS de DigitalOcean, con Docker Compose (ADR-020). El runbook, del
primer despliegue a la recuperación, es `docs/runbooks/vps.md`.

| Ruta | Qué es |
|---|---|
| `compose.yml` | El stack: Supabase autoalojado (solo lo que se usa), hr-engine, Redis, career site, Caddy con el panel y el diagnóstico gratuito, y Cloudflare Tunnel |
| `.env.example` | La plantilla del `.env` del servidor (`/opt/vortex/.env`) |
| `caddy/` | El `Caddyfile` y la imagen de Caddy con el panel y el diagnóstico ya construidos |
| `career-site/` | La imagen del career site (Next.js `standalone`) |
| `supabase/` | El gateway (Envoy) y los SQL de arranque del Supabase autoalojado oficial, vendorizados; `db/vortex.sql` es propio |
| `scripts/` | Provisionar el servidor, generar secretos, desplegar, migrar, respaldar y restaurar |
| `systemd/` | El timer del respaldo nocturno |
| `pruebas/` | La prueba local de punta a punta: `pruebas/probar_en_local.sh` |

Antes de llevar un cambio al servidor se corre la prueba local (con Docker en marcha, y
pnpm y uv; en Windows, `PYTHON=python`):

```bash
infra/vps/pruebas/probar_en_local.sh
```

Levanta el stack con imágenes construidas en local, con los sitios en
`localhost:8080` (career site), `:8081` (panel), `:8082` (API) y `:8083` (diagnóstico),
y corre contra él:

- el e2e del plan gratis, en modo despliegue (`E2E_REMOTO=1 pnpm e2e:flujo`): invitación,
  vacante, aplicaciones con CV, el worker del stack, el gancho, el .zip y eliminar;
- `humo.py`: el borde (Studio no se publica, 401 sin apikey, sin alta sin invitación) y las
  plantillas de correo en Mailpit; y el diagnóstico gratuito: registrar uno por
  `/api/diagnostico`, que anon no lo lea, el freno por correo y que el aviso llegue a
  Mailpit;
- un respaldo a un S3 local, el borrado de la base y los CVs, la restauración, la
  comparación con lo de antes y el e2e otra vez.

Al final lo baja todo, volúmenes incluidos.
