# ADR-012 · Backend hosting: defer Coolify, target Fly.io / Railway

- **Status:** Accepted
- **Fecha:** 2026-05-25
- **Decisores:** Ilyra
- **Relacionado:** ADR-010 (frontends Vercel), ADR-009 (vendoring Paperclip/OpenClaw)

## Contexto

El plan original (`09_PROJECT_PLAN.md`, Cycle 1 tareas 1.1 + 1.2) propone **Coolify self-host en VPS Hetzner CX31** ($15/mo) para Paperclip (control-plane), OpenClaw (agent-plane) y hr-engine. Después de cerrar foundation, evaluamos:

- Coolify exige ops manual: certificados Let's Encrypt, healthchecks, rotación de logs, backups Postgres.
- Hr-engine puede correr local con docker-compose mientras Cycle 1 se itera contra Supabase Cloud (managed Postgres + pgvector).
- Paperclip/OpenClaw todavía no están vendored ni adaptados; deployarlos en Coolify hoy es prematuro.

## Decisión

**Diferir Coolify a post-Cycle 2.** Para los engines cuando sean necesarios:

| Componente | Hosting Cycle 1 | Hosting Cycle 2-4 | Producción ≥ Cycle 5 |
|---|---|---|---|
| `apps/*` frontends | Vercel | Vercel | Vercel + dominio propio |
| `services/hr-engine` (FastAPI + Celery) | Local docker-compose | **Fly.io** (api + worker como apps separadas) | Fly.io con autoscaling |
| `services/control-plane` (Paperclip Node) | — (no existe aún) | **Fly.io** | Fly.io |
| `services/agent-plane` (OpenClaw TS) | — | **Fly.io** (necesita WebSockets persistentes) | Fly.io |
| `services/sales-engine` | — | **Fly.io** (Cycle 3) | Fly.io |
| Postgres + pgvector | Local docker | **Supabase Cloud** (free tier 500 MB) | Supabase Cloud Pro |
| Redis (Celery broker) | Local docker | **Upstash Redis** (free tier 10k cmd/día) | Upstash Pay-as-you-go |

**Por qué Fly.io:**
- Soporta long-running workers (Celery, WebSockets) — Vercel/Cloudflare Workers no.
- Region `gru` (São Paulo) para latencia LATAM consistente con frontends.
- Pricing predecible: $1.94/mo por VM shared-cpu-1x · 256MB. Para Cycle 2 estimamos 4 VMs (~$8/mo) — más barato que Hetzner.
- Despliegue por `fly deploy` desde GitHub Actions con `flyctl`.

**Alternativa con misma puntuación: Railway.** Decisión final entre los dos al iniciar Cycle 2 según UX de deploy.

## Consecuencias

### Positivas

- Cycle 1 corre 100% local + Supabase Cloud (gratis). Cero costo de infra durante MVP.
- Cuando se necesite deploy de hr-engine (semana 2 para demo), Fly.io toma < 30 min.
- Coolify queda disponible para Enterprise tier (Q3-Q4) donde clientes pidan self-host.

### Negativas

- Hay que escribir Dockerfiles + `fly.toml` por servicio cuando llegue Cycle 2. Trabajo diferido, no eliminado.
- Lock-in suave a Fly. Mitigado: los Dockerfiles ya son standalone (multi-stage, no Fly-specific).

## Acciones

- [x] Eliminar tareas Coolify de `next-steps.md` Cycle 1 wk1 (1.1, 1.2). Reemplazar por "preparar imágenes Docker".
- [ ] Cycle 2 wk1: provisionar app Fly.io para `hr-engine` (api + worker), `agent-plane`, `control-plane`.
- [ ] Documentar en `docs/runbooks/deploy.md` el flow Fly.io.
- [ ] Coolify queda como opción para Enterprise tier on-prem en `docs/specs/enterprise-tier.md` (futuro).
