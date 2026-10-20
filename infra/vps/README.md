# infra/vps

Producción en un solo VPS de DigitalOcean, con Docker Compose (ADR-020). El runbook, del
primer despliegue a la recuperación, es `docs/runbooks/vps.md`.

| Ruta | Qué es |
|---|---|
| `compose.yml` | El stack: Supabase autoalojado (solo lo que se usa), hr-engine, Redis, career site, Caddy con el panel y Cloudflare Tunnel |
| `.env.example` | La plantilla del `.env` del servidor (`/opt/vortex/.env`) |
| `caddy/` | El `Caddyfile` y la imagen de Caddy con el panel ya construido |
| `career-site/` | La imagen del career site (Next.js `standalone`) |
| `supabase/` | El gateway (Envoy) y los SQL de arranque del Supabase autoalojado oficial, vendorizados; `db/vortex.sql` es propio |
| `scripts/` | Provisionar el servidor, generar secretos, desplegar, migrar, respaldar y restaurar |
| `systemd/` | El timer del respaldo nocturno |
| `pruebas/` | La prueba local de punta a punta: `pruebas/probar_en_local.sh` |

Antes de llevar un cambio al servidor se corre la prueba local (con Docker en marcha):

```bash
PYTHON=python infra/vps/pruebas/probar_en_local.sh
```

Levanta el stack con imágenes construidas en local y lo recorre de punta a punta:

- invitación y enlace mágico (Mailpit);
- una vacante y el career site;
- aplicaciones con CV y el worker;
- respaldo a un S3 local, borrado y restauración.

Al final lo baja todo.
