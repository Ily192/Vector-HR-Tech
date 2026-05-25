# Vortex Ops

> **Hackeando la rutina, liberando el talento.** — *Vector HR Tech*

Operations Engine agentic, multi-tenant, self-hostable. Un solo control plane orquesta agentes autónomos que ejecutan procesos end-to-end de **HR + Sales + Cross-functional ops**, con governance de presupuesto, multi-canal conversacional (WhatsApp, Telegram, Slack, Google Chat, Teams) y vibe-codeable por diseño.

```
┌─ Capa 4 ────────────────────────────────────────────┐
│ Frontends (Next.js 14 + Vite + shadcn/ui)           │
│  career-site · candidate · hrbp · orgchart          │
├─ Capa 3 ────────────────────────────────────────────┤
│ Execution engines (FastAPI + Celery + Redis)        │
│  hr-engine · sales-engine                           │
├─ Capa 2 ────────────────────────────────────────────┤
│ Agent plane (OpenClaw + gstack SKILL.md)            │
│  agentes HR · agentes Sales · agentes Cross         │
├─ Capa 1 ────────────────────────────────────────────┤
│ Control plane (Paperclip)                           │
│  org chart · budget · heartbeats · approvals        │
└──────────────────────────────────────────────────────┘
                       │
              Supabase (Postgres + pgvector + RLS)
```

## Quick start (cuando exista código)

```bash
pnpm install
pnpm dev          # arranca apps + services en local
pnpm test         # corre tests de todos los workspaces
pnpm e2e          # Playwright E2E
```

## Estructura del repo

```
vortex-ops/
├── apps/                    Frontends (cada uno deploy independiente)
│   ├── career-site/         Next.js 14 — landing pública
│   ├── candidate/           Vite + React — portal candidato + tests psicométricos
│   ├── hrbp/                Vite + React — cockpit HRBP
│   └── orgchart/            Next.js 14 — Org Chart Vortex (mirror Paperclip)
│
├── services/                Backends
│   ├── control-plane/       Paperclip (Node.js) — governance
│   ├── agent-plane/         OpenClaw (TS ESM) — runtime conversacional
│   ├── hr-engine/           FastAPI + Celery — workers HR
│   └── sales-engine/        FastAPI + Celery — workers Sales (basado en SDR-prospection)
│
├── packages/                Compartido
│   ├── ui/                  shadcn/ui customizada con Vector HR brand
│   ├── design-tokens/       tokens.json + Tailwind preset
│   ├── supabase-client/     cliente tipado + RLS helpers
│   ├── types/               Zod schemas + TS types compartidos
│   └── skills-sdk/          helpers para crear SKILL.md (gstack-style)
│
├── .agents/skills/          Skills de los agentes (formato gstack)
│   ├── chro-intake/
│   ├── sourcer/
│   └── ...
│
├── infra/                   IaC + deploy
│   ├── coolify/             docker-compose de referencia
│   ├── docker/              Dockerfiles
│   ├── supabase/            migrations + seed
│   └── terraform/           (opcional) cloud infra
│
├── docs/                    Documentación PMO
│   ├── 00_README.md
│   ├── 01_PROJECT_CHARTER.md
│   ├── ...
│   ├── adr/                 Architecture Decision Records
│   ├── specs/               Especificaciones funcionales
│   ├── runbooks/            Operativa día a día
│   └── onboarding/          Guías para nuevos devs
│
├── evals/                   Evals de skills (gstack pattern)
├── scripts/                 Tooling (codegen, migration helpers)
└── .github/workflows/       CI/CD
```

## Documentación

Empieza por **[docs/00_README.md](docs/00_README.md)**. El plan completo está en 12 documentos numerados.

## Stack

| Capa | Tecnología |
|---|---|
| Frontend | Next.js 14 (App Router) · Vite · React 18 · TypeScript 5.5 · Tailwind 3 · shadcn/ui · TanStack Query · Zustand |
| Backend | FastAPI · SQLAlchemy 2 async · Alembic · Celery · Redis |
| Control plane | Paperclip (Node.js + Postgres) |
| Agent plane | OpenClaw (TS ESM strict) + gstack SKILL.md |
| AI | OpenAI gpt-4o + gpt-4o-mini · Google Gemini 1.5 · text-embedding-3-small |
| DB | Supabase (Postgres 15 + pgvector + RLS) |
| Auth | Supabase Auth + JWT + Paperclip run-tokens |
| Observability | OpenTelemetry · Sentry · Grafana · Better Stack logs |
| CI/CD | GitHub Actions · Coolify · Vercel (apps) |
| Testing | Vitest · Pytest · Playwright · k6 (load) · Zod (runtime) |

## Brand

**Vector HR Tech** opera **Vortex Ops**. Paleta:

| Token | Hex | Rol |
|---|---|---|
| `--vector-cian-dark` | `#1E1B4B` | Ancla / fondos / autoridad |
| `--vector-cian-electric` | `#00FFFF` | Tech / IA / acentos |
| `--vector-orange` | `#FF7F00` | CTA / rebeldía |
| `--vector-white` | `#FFFFFF` | Claridad |

Detalle en [docs/04_BRAND_AND_DESIGN_SYSTEM.md](docs/04_BRAND_AND_DESIGN_SYSTEM.md).

## License

Open core (TBD). Componentes propietarios bajo licencia comercial Vector HR Tech.

---

*v0.1.0 — 2026-05-08*
