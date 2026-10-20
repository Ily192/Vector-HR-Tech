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
| [010](010-vercel-frontends.md) | Frontends en Vercel + subdominio default hasta revenue | Superseded by ADR-020 (para el MVP) |
| [011](011-typography-inter.md) | Tipografía Inter (display) + Lato (body), free | Superseded por la marca v2 ([branding-v2](../brand/branding-v2.md): Figtree + JetBrains Mono) |
| [012](012-backend-hosting-deferred.md) | Backends en Fly.io (Cycle 2+); Coolify diferido | Superseded by ADR-020 (para el MVP) |
| [013](013-brand-placeholder.md) | Wordmark + Lucide como brand visual; logo diferido | Accepted |
| [014](014-test-psicometrico-iframe.md) | Test psicométrico vía iframe del HTML legacy (v0) | Accepted |
| [015](015-tenant-identity-in-app-metadata.md) | Identidad de tenant en `app_metadata`; privilegio de plataforma fuera de `profiles` | Accepted |
| [016](016-logica-de-negocio-fuera-de-la-ui.md) | La lógica de negocio vive en el backend; la UI solo la presenta | Accepted |
| [017](017-career-site-modulo-gratuito.md) | El career site es el módulo gratuito de Vortex, no un sitio de marketing | Accepted |
| [018](018-preseleccion-ia-del-plan-gratis.md) | Preseleccionar con IA el plan gratis: a ciegas, con topes y por instrucción de la empresa | Superseded by ADR-019 (siguen vigentes §10-§12 y §14) |
| [019](019-plan-gratis-sin-ia.md) | El plan gratis no usa IA: descarga en .zip y una coincidencia de skills como gancho | Accepted |
| [020](020-plataforma-en-un-vps.md) | Toda la plataforma en un VPS, con Supabase autoalojado y Docker Compose | Accepted |

## Cómo escribir una ADR

1. Copiar plantilla de `template.md`.
2. Numerar secuencialmente.
3. Status: `Proposed` → `Accepted` / `Rejected` / `Superseded by NNN`.
4. PR con la ADR antes (o junto) al PR del cambio que decide.
