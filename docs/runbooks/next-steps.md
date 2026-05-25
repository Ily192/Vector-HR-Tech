# Next steps — qué falta por ejecutar

> Lista viva. Actualizar al cierre de cada sesión.
> Última actualización: 2026-05-08

## Inmediato — Cierre de Cycle 0 (próxima sesión, ~2-3h)

### 1. Verificación end-to-end del foundation

Objetivo: probar que `pnpm install && pnpm dev` y los engines arrancan sin errores en máquina limpia.

```bash
cd Vortex-Ops

# Levantar Postgres + Redis
docker compose -f infra/docker/docker-compose.dev.yml up -d

# Aplicar schema
psql postgresql://vortex:vortex@localhost:5432/vortex_dev \
  -f infra/supabase/migrations/0001_initial_schema.sql
psql postgresql://vortex:vortex@localhost:5432/vortex_dev \
  -f infra/supabase/seed.sql

# Frontends
pnpm install
pnpm tokens:build
pnpm dev   # career-site:3000, hrbp:3001

# Backend (otra terminal)
cd services/hr-engine
cp .env.example .env
uv sync --dev
uv run uvicorn app.main:app --reload --port 8000

# Worker (otra terminal)
uv run celery -A app.workers.celery_app worker --loglevel=info --queues=hr

# Tests
pnpm test
cd services/hr-engine && uv run pytest tests/unit -v
```

**Riesgo conocido:** algunas versiones de packages (`@vortex/ui`, etc.) pueden tener desajustes que se vean al primer `pnpm install`. Iterar con Claude/Cursor para arreglar.

### 2. Init Git + primer commit + repo GitHub

```bash
cd Vortex-Ops
git init
git add .
git commit -m "feat(foundation): cycle 0 — repo skeleton, docs PMO, brand, schema, hr-engine stub"
git tag v0.1.0

# Crear repo privado en GitHub
gh repo create vector-hr-tech/vortex-ops --private --source=. --remote=origin --push

# Configurar branch protection en main
gh api -X PUT repos/vector-hr-tech/vortex-ops/branches/main/protection \
  -F required_status_checks.strict=true \
  -F enforce_admins=true \
  -F required_pull_request_reviews.required_approving_review_count=1 \
  -F restrictions=
```

### 3. Configurar secretos GitHub Actions

Necesarios para que CI pase:
- `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID_*` (4 apps)
- `COOLIFY_TOKEN`, `COOLIFY_WEBHOOK_STAGING`, `COOLIFY_WEBHOOK_PROD`
- `SENTRY_TOKEN`, `CODECOV_TOKEN`, `LHCI_GITHUB_APP_TOKEN`
- `TURBO_TOKEN`, `TURBO_TEAM`

Idealmente vía **Doppler** (free tier) sincronizado a GitHub Actions environments.

### 4. Crear Supabase Cloud project

- New project en supabase.com (free tier OK para empezar).
- Copiar URL + anon key + service role key a Doppler.
- Aplicar `0001_initial_schema.sql`: `supabase db push`.
- Habilitar pgvector extension en dashboard.
- Configurar **trigger `on_auth_user_created`** que pobla `profiles` con `empresa_id` custom claim al sign-up.

### 5. Decisión nombre comercial final

- **Vortex Ops** confirmado como producto.
- Pendiente: ¿el repo público se llamará `vortex-ops` o `vector-hr/vortex-ops`?
- Comprar dominios: `vortex-ops.com`, `vector-hr.tech` (verificar disponibilidad).

---

## Cycle 1 — MVP HR Pipeline (semanas 1-2 ≈ 60h humano + 120h vibe)

### Semana 1

- [ ] **1.1** Levantar Paperclip self-host en Coolify VPS (Hetzner CX31 ~$15/mo).
- [ ] **1.2** Levantar OpenClaw + adapter Google Chat (gratis para empezar).
- [ ] **1.3** Vibe-codear `hr-engine/workers/sourcer.py` real (de stub a funcional):
  - Vector match en pgvector
  - Gemini 1.5 Flash scoring
  - Persistencia en `applications`
- [ ] **1.4** Vibe-codear `hr-engine/workers/cv_evaluator.py`:
  - Pydantic schema strict para output (mirror de `CvEvaluationSchema` en `packages/types`)
  - Eval golden set inicial (10 CVs etiquetados)
- [ ] **1.5** Trigger Supabase `on_auth_user_created` para poblar `profiles.empresa_id`.
- [ ] **1.6** Wireframes en Figma: career-site, candidate, hrbp (3-4h).

### Semana 2

- [ ] **2.1** Career-site: form de aplicación funcional (CV upload → Supabase Storage).
- [ ] **2.2** Candidate portal: dashboard + status + ruta `/test/:token` para Test-psicometricos embebido.
- [ ] **2.3** HRBP cockpit: kanban pipeline conectado a Supabase realtime + detalle candidato.
- [ ] **2.4** Skill `chro-intake` (`SKILL.md` + golden set).
- [ ] **2.5** Skill `cv-evaluator` con eval Pearson r ≥ 0.75.
- [ ] **2.6** Wire OpenClaw → hr-engine via run-token (validación JWT en hr-engine).
- [ ] **2.7** E2E test Playwright: "Subir CV → ver score en hrbp en < 2 min".
- [ ] **2.8** Loom demo público de 5 min.

### DoD Cycle 1

- ✅ Subir CV en career-site → ver score en hrbp en < 2 min wall-clock.
- ✅ Coverage ≥ 60% en `services/hr-engine`.
- ✅ Lighthouse ≥ 85 en career-site.
- ✅ RLS tests pasan con multi-tenant fixture.
- ✅ Loom demo grabado.

---

## Cycles 2-4 (resumen, detalle en `docs/09_PROJECT_PLAN.md`)

- **Cycle 2 (sem 4-5):** scheduler + interviewer + onboarder + constancia_gen + WhatsApp Business adapter + 50 candidatos en producción con Siete.
- **Cycle 3 (sem 7-8):** sales-engine multi-tenant (migrar SDR-prospection completo).
- **Cycle 4 (sem 10-11):** lanzamiento público open-source + Stripe billing + 5 clientes Pro firmados → $1.5k MRR.

---

## Decisiones pendientes / open questions

| Tema | Pregunta | Cuándo resolver |
|---|---|---|
| Tipografía | ¿Comprar licencia Proxima Nova ($300-500) o usar Inter (free)? | Antes Cycle 1 wk2 (UI usa fonts) |
| Hosting | Coolify VPS Hetzner vs Fly.io vs Railway | Cycle 1 wk1 |
| WhatsApp provider | 360dialog vs Twilio vs Meta direct | Cycle 2 |
| Cliente piloto pagado | ¿Usar contactos de Siete o LinkedIn outbound frío? | Cycle 1 cooldown |
| Open-source | ¿Liberar Paperclip+OpenClaw+4 skills básicas? ¿AGPLv3 o Elastic License? | Cycle 4 |
| Logo | ¿Diseñar uno propio o usar wordmark + ícono de Lucide hasta tener revenue? | Cycle 1 wk2 |
| Test-psicometricos | ¿Migrar a React component o mantener iframe del HTML estático? | Cycle 1 wk2 |

---

## Riesgos en watch (top 3 del Risk Register)

1. **R-07 Bus factor 1.** Mitigación activa: docs obsesivas + repo público mes 4.
2. **R-15 Burnout.** Mitigación: respetar cooldown semana, no trabajar fines de semana.
3. **R-12 Vibe coding sin review.** Mitigación: DoD obligatorio + code-review agent en CI.

---

## Métricas a empezar a medir desde Cycle 1

- Lead time (commit → prod) — auto-tracked por `nightly.yml`.
- Deploy frequency — auto-tracked.
- Eval pass rate por skill — auto-tracked en CI.
- Cost USD por run de agente — emitido por hr-engine, agregado en Grafana.
- Tiempo de pipeline HR (apply → score) — métrica de negocio principal.
