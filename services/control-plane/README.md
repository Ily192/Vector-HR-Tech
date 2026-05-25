# control-plane (Paperclip)

> **Cycle 1 · tarea 1.1 — Paperclip self-host.**
> Node.js + Postgres. Vendored (no submódulo) — ver ADR-009.

Scaffold pendiente. El plan:

1. Copiar `paperclip-master` del Portafolio como base.
2. Adaptar al esquema multi-tenant `empresas/profiles` (ya existe en Supabase).
3. Emitir run-tokens JWT con TTL 5 min (`empresa_id`, `agent_skill`, `run_id`, `cost_cap_usd`) — ver ADR-005.
4. Endpoint `POST /runs` que firma + persiste en `activity_log`.

Responsabilidades del control plane:

- Org chart canónico (mirror en `apps/orgchart/`)
- Budget governance (cost caps por tenant y por run)
- Heartbeats + health de agentes
- Approvals (escalation requirements: cuándo un humano debe firmar antes que el agente actúe)
- Activity log append-only con hash chain

Hosting: **Fly.io / Railway** (ver ADR-012). No Vercel — proceso persistente con DB pool y cron jobs.
