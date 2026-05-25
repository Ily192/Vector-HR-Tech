# Session log

Bitácora de sesiones de trabajo Ilyra + Claude. Más reciente arriba.

---

## 2026-05-08 · Sesión 1 — Foundation completa

**Duración:** ~1 jornada · **Modo:** Auto + vibe coding · **Modelo:** Claude Opus 4.7 (1M)

### Lo que se hizo

#### Análisis y benchmarking
- Análisis del Portafolio completo: identificación de Paperclip, OpenClaw, gstack, SDR-prospection, AI-SDR, portal-de-talentos, Portal-HR-TH, Test-psicometricos, brochure-talent.
- Benchmark v1 con n8n: `Portal-HR/01_BENCHMARK_v1.md`.
- Replanteo arquitectura v2 (n8n eliminado): `Portal-HR/02_ARCHITECTURE_v2.md`.

#### Decisiones de producto
- **Marca:** Vector HR Tech (paraguas) opera **Vortex Ops** (producto).
- **Slogan:** *Hackeando la rutina, liberando el talento.*
- **Pricing v2:** Starter $149 / Pro $499 / Scale $1.5k / Enterprise $3.5-7k. Break-even mes 4-6.
- **Bundle:** HR + Sales engines en mismo control plane (compite contra Eightfold *y* Apollo).
- **n8n out:** los 14 JSON se vibe-codean a workers Python (patrón SDR-prospection).

#### Repo `Vortex-Ops/` creado y poblado (112 archivos)

**Documentación PMO (13 docs):**
- `README.md` raíz · `docs/00_README.md` index
- `01_PROJECT_CHARTER.md` — visión, objetivos SMART 12 meses, scope, DoD
- `02_METHODOLOGY.md` — Shape Up adaptado (cycles 2 sem + cooldown 1 sem) + trunk-based + DORA
- `03_ARCHITECTURE.md` — C4, componentes, ERD, flow E2E
- `04_BRAND_AND_DESIGN_SYSTEM.md` — paleta, tipografía, motion, a11y WCAG 2.2 AA
- `05_TECH_STACK_AND_BEST_PRACTICES.md` — alineado con Linear/Vercel/Stripe/Anthropic
- `06_TESTING_STRATEGY.md` — pirámide, evals para skills, RLS tests, performance budgets
- `07_CICD_AND_DEVOPS.md` — pipelines, canary 5%→100%, expand/contract migrations
- `08_SECURITY_AND_COMPLIANCE.md` — STRIDE, RLS, RBAC, LGPD/Habeas Data, OWASP
- `09_PROJECT_PLAN.md` — Cycles 0-4 detallados
- `10_RISK_REGISTER.md` — 20 riesgos con P×I (críticos: bus factor 1, burnout)
- `11_QUALITY_GATES.md` — DoR/DoD por tipo de cambio
- `12_OBSERVABILITY.md` — logs JSON, OTel, SLOs, cost observability, audit log

**ADRs (9 accepted):** 001 no-n8n · 002 monorepo pnpm/turbo · 003 trunk-based · 004 RLS defense-in-depth · 005 run-tokens JWT 5 min · 006 SKILL.md gstack format · 007 pgvector (no Pinecone) · 008 LLM routing (Gemini default, gpt-4o reasoning, Claude code) · 009 vendoring (no submodule).

**Apps frontend runnable:**
- `apps/career-site/` (Next.js 14 App Router) — hero brandeada cian dark + glow naranja, `/vacantes` listado, `/vacantes/[slug]` detalle, headers de seguridad, Inter+Lato.
- `apps/hrbp/` (Vite + React 18 SPA) — dark mode default, cockpit con KPIs + pipeline kanban placeholder, TanStack Query.

**Packages compartidos:**
- `packages/types/` — Zod schemas (`Empresa`, `Vacante`, `Candidato`, `Application`, `JwtClaims`, `RunTokenClaims`, `CvEvaluation`, `Campaign`, `Icp`).
- `packages/ui/` — `Button` con variants brand, `Card`, `Badge` (variant `ai` con shadow cian), `Wordmark`.
- `packages/design-tokens/` — `tokens.json` Style Dictionary, `tailwind.preset.js`, `theme.css` shadcn light+dark.

**Backend hr-engine:**
- `services/hr-engine/` con FastAPI 0.115 + Celery 5 + structlog + Sentry + OTel.
- `pyproject.toml` con `uv` deps, Dockerfile multi-stage, settings tipadas Pydantic.
- `tenant_guard` middleware, run-token verification skeleton.
- Primer worker `sourcer.py` con patrón `_run + @task` (heredado de SDR-prospection) — stub funcional.
- Endpoints `/health`, `/ready`, `/api/sourcer/run`.
- Test unit `test_sourcer.py`.

**Datos:**
- `infra/supabase/migrations/0001_initial_schema.sql` — empresas, profiles, vacantes (con `vector(1536)` HNSW), candidatos, applications, runs, activity_log append-only con trigger inmutable, **RLS completa** + helpers `auth.empresa_id()` y `auth.role()`.
- `infra/supabase/seed.sql` — Vector HR + Siete + 2 vacantes mock.
- `infra/docker/docker-compose.dev.yml` — pgvector/pg15 + Redis 7.

**CI/CD (4 workflows):**
- `ci.yml` — lint TS+Py, typecheck, unit, integration (testcontainers), RLS tests, evals condicional, semgrep, gitleaks, dependency-review, bundle budget.
- `preview-deploy.yml` — Vercel preview por app + Lighthouse CI + Playwright smoke.
- `release.yml` — build & push imágenes + cosign sign + SBOM + Trivy + canary 5%→monitor 10min→100%.
- `nightly.yml` — eval suite full + RLS paranoid scan + DORA report semanal.
- `.github/CODEOWNERS`, `dependabot.yml`, `PULL_REQUEST_TEMPLATE.md`.

**Skills:**
- `.agents/skills/sourcer/SKILL.md` + `agents/openai.yaml` (formato gstack).

**Onboarding + Runbooks:**
- `docs/onboarding/README.md` (setup paso a paso).
- `docs/runbooks/local-dev.md`, `deploy.md`, `rollback.md`, `postmortem-template.md`.

**Tooling raíz:**
- `package.json` con scripts (`dev`, `build`, `test`, `e2e`, `tokens:build`).
- `pnpm-workspace.yaml`, `turbo.json`, `tsconfig.base.json`, `biome.json`.
- `.env.example`, `.gitignore`.

### Estado del proyecto al cierre

- **Cycle 0 (Foundation):** ✅ completo en estructura. Falta verificación runtime (ver "Pendiente").
- **Repo no inicializado en Git** todavía. No hay `.git/` ni remote.
- **No hay Supabase Cloud project** creado aún (solo local con docker-compose).
- **No hay claves API reales** en `.env` (solo `.env.example`).

### Pendiente para próxima sesión

Ver `docs/runbooks/next-steps.md` (lista viva).

---

<!-- Próxima sesión: insertar nuevo bloque aquí arriba con fecha YYYY-MM-DD -->
