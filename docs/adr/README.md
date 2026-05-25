# Architecture Decision Records (ADRs)

Formato Michael Nygard. Uno por decisión arquitectónica relevante.

## Estado

| ID | Título | Estado |
|---|---|---|
| [001](001-no-n8n.md) | Eliminar n8n; vibe-codear flows a FastAPI + Celery | Accepted |
| [002](002-monorepo-pnpm-turbo.md) | Monorepo pnpm + Turborepo, servicios Python independientes | Accepted |
| [003](003-trunk-based-feature-flags.md) | Trunk-based development con feature flags | Accepted |
| [004](004-supabase-rls-defense-in-depth.md) | Supabase RLS como última línea de defensa multi-tenant | Accepted |
| [005](005-paperclip-run-tokens.md) | Paperclip emite run-tokens JWT 5 min | Accepted |
| [006](006-skill-md-as-agent-unit.md) | SKILL.md (gstack format) como unidad de agente | Accepted |
| [007](007-pgvector-not-pinecone.md) | pgvector en Supabase, no Pinecone | Accepted |
| [008](008-llm-routing-policy.md) | Routing LLMs (Gemini default, gpt-4o reasoning, Claude code) | Accepted |
| [009](009-vendoring-paperclip-openclaw.md) | Vendoring (no submodule) de paperclip-master y openclaw-main | Accepted |
| [010](010-vercel-frontends.md) | Frontends en Vercel + subdominio default hasta revenue | Accepted |
| [011](011-typography-inter.md) | Tipografía Inter (display) + Lato (body), free | Accepted |
| [012](012-backend-hosting-deferred.md) | Backends en Fly.io (Cycle 2+); Coolify diferido | Accepted |
| [013](013-brand-placeholder.md) | Wordmark + Lucide como brand visual; logo diferido | Accepted |
| [014](014-test-psicometrico-iframe.md) | Test psicométrico vía iframe del HTML legacy (v0) | Accepted |

## Cómo escribir una ADR

1. Copiar plantilla de `template.md`.
2. Numerar secuencialmente.
3. Status: `Proposed` → `Accepted` / `Rejected` / `Superseded by NNN`.
4. PR con la ADR antes (o junto) al PR del cambio que decide.
