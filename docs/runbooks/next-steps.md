# Next steps — qué falta por ejecutar

> Lista viva. Actualizar al cierre de cada sesión.
> Última actualización: **2026-05-25** (sesión 2).

## TL;DR

Cycle 0 cerrado en lo que dependía de Claude/local. Avance Cycle 1 wk1 ~50%:
workers `sourcer` + `cv_evaluator` listos, supabase-client wired, ADRs 010-014 documentadas. Falta acción del user para conectar servicios externos.

---

## Bloqueado por el user (no se puede hacer en local)

### 1. Push a `Ily192/Vector-HR-Tech` (repo personal, público)

Repo target: https://github.com/Ily192/Vector-HR-Tech (público, owner `Ily192`).
Auth `gh` actual (`ilyra-dev`) solo tiene pull → re-auth como `Ily192` antes de pushear:

```bash
gh auth login            # GitHub.com → HTTPS → browser → loguear como Ily192
gh auth switch -u Ily192 # activar la cuenta
gh auth status           # confirmar Active: Ily192
```

Luego desde la raíz del repo:

```bash
git remote add origin https://github.com/Ily192/Vector-HR-Tech.git
git push --force-with-lease origin main
```

**Por qué force-push:** el remoto tenía 1 commit `b4d41f2 "Add files via upload"` (2026-03-14) con un scaffold de Google AI Studio (Vite single-app, Login/Dashboard/Profile) totalmente incompatible con nuestro pnpm monorepo. Sin valor mergeable: chocan `package.json`/`tsconfig.json`/`vercel.json` a nivel root y la convención `src/` vs `apps/*/src/`. El commit queda preservado en el reflog de GitHub (`b4d41f2`) si alguna vez se necesita.

**Branch protection** (deferido — repo es público y solo trabaja Ilyra, no hay PRs externos en Cycle 1):

```bash
# Cuando se sumen contributors:
gh api -X PUT repos/Ily192/Vector-HR-Tech/branches/main/protection \
  -F required_status_checks.strict=true \
  -F required_status_checks.contexts[]='Lint TS' \
  -F required_status_checks.contexts[]='Typecheck TS' \
  -F required_status_checks.contexts[]='Unit tests (TS)' \
  -F required_status_checks.contexts[]='Lint Python' \
  -F required_status_checks.contexts[]='Typecheck Python (mypy)' \
  -F required_status_checks.contexts[]='Multi-tenant RLS tests' \
  -F enforce_admins=false \
  -F required_pull_request_reviews.required_approving_review_count=1 \
  -F restrictions=
```

### 2. Provisionar Supabase Cloud project

- supabase.com → New project (region: `sa-east-1` para LATAM).
- Habilitar extensión `vector` desde dashboard.
- Aplicar las 3 migrations en orden:
  ```bash
  supabase link --project-ref <PROJECT_REF>
  supabase db push  # aplica infra/supabase/migrations/0001..0003
  psql "$DATABASE_URL" -f infra/supabase/seed.sql  # solo dev
  ```
- Copiar `URL`, `anon key`, `service_role key` a Doppler.

### 3. Provisionar proyectos Vercel (1 por app)

Para `career-site` y `hrbp`:

- New Project → Import Git Repository → seleccionar `vortex-ops`.
- Root Directory: `apps/career-site` (y luego `apps/hrbp`).
- Framework Preset: auto-detect (Next.js / Vite).
- Build/Install commands: Vercel los lee de `apps/<name>/vercel.json` — ya commiteado.
- Env vars: copiar desde Doppler (`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_HR_ENGINE_URL`, `NEXT_PUBLIC_SENTRY_DSN`; para hrbp prefix `VITE_`).
- Production domain: dejar `*.vercel.app` por ahora (ADR-010).

### 4. Configurar secrets en GitHub Actions

Doppler → integration con GitHub → sync env `prd` a Repository secrets.

Secrets necesarios:
- `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID_career-site`, `VERCEL_PROJECT_ID_hrbp`
- `SENTRY_TOKEN`, `CODECOV_TOKEN`, `LHCI_GITHUB_APP_TOKEN`
- `TURBO_TOKEN`, `TURBO_TEAM` (opcional — para cache remote)

`COOLIFY_*` secrets diferidos a post-Cycle 2 (ver ADR-012).

---

## Cycle 1 — MVP HR Pipeline (semanas 1-2)

### Semana 1 (en curso)

- [x] **1.3 (50%)** `sourcer.py` vibe-codeado — falta probar end-to-end con Supabase Cloud + LLM real.
- [x] **1.4 (60%)** `cv_evaluator.py` implementado — falta poblar golden set (10 CVs reales etiquetados).
- [x] **1.5** Trigger Supabase `on_auth_user_created` (ya en `0003_auth_hooks.sql`).
- [ ] **1.6** Wireframes: hechos en markdown (`docs/specs/cycle-01-wireframes.md`). Skip Figma para v0.
- [ ] **1.7** `packages/design-tokens` build (validado en sesión 2 — Tailwind preset funciona).

### Semana 2

- [ ] **2.1** Career-site: form de aplicación funcional en `/vacantes/[slug]/aplicar` con CV upload a Supabase Storage (bucket `cvs/`, RLS por empresa_id). Server Action.
- [ ] **2.2** Candidate app: scaffold Vite + React, rutas `/`, `/applications/:id`, `/test/:token`, `/profile`. Copiar HTML legacy a `apps/candidate/public/psicometrico/`.
- [ ] **2.3** HRBP cockpit: `/vacantes/:id` kanban con `@dnd-kit/core` + Supabase Realtime channel `applications:vacante_id=eq.{id}`. Botón `+ Sourcing` dispara `sourcer.run`.
- [ ] **2.4** Skill `chro-intake` — SKILL.md (gstack) + golden set en `evals/chro-intake/`. Se invoca cuando un HR Director sube una vacante por chat (Google Chat adapter).
- [ ] **2.5** Poblar `evals/cv-evaluator/golden.jsonl` con ≥ 10 CVs reales (anonimizados) de Siete. Correr `runner.py --fail-below-threshold` y subir Pearson r de 0.6 a ≥ 0.75.
- [ ] **2.6** Run-token verification en hr-engine — `python-jose` decode + claims check (empresa_id, agent_skill, run_id, cost_cap_usd) (ADR-005). Hoy el API endpoint recibe empresa_id en body — pasar a header `Authorization: Bearer <run-token>`.
- [ ] **2.7** E2E Playwright: "Subir CV en career-site → ver score en hrbp en < 2 min wall-clock". Test corre contra Vercel preview + Supabase Cloud staging.
- [ ] **2.8** Loom demo público de 5 min.

### DoD Cycle 1 (revisado)

- ✅ Subir CV en career-site → ver score en hrbp en < 2 min wall-clock.
- ✅ Coverage ≥ 60% en `services/hr-engine`.
- ✅ Lighthouse ≥ 85 en career-site (Vercel preview).
- ✅ RLS tests pasan con multi-tenant fixture (ya verde — solo falta correr CI).
- ✅ Loom demo grabado.
- ✅ Pearson r de `cv-evaluator` ≥ 0.75 en golden set ≥ 10 cases.

---

## Cycles 2-4 (resumen)

- **Cycle 2 (sem 4-5):** Provisionar Fly.io para hr-engine + Paperclip vendoring + OpenClaw vendoring (ADR-009). Workers `scheduler`, `interviewer`, `onboarder`, `constancia_gen`. WhatsApp adapter. 50 candidatos reales con Siete.
- **Cycle 3 (sem 7-8):** sales-engine multi-tenant (ver `services/sales-engine/README.md`).
- **Cycle 4 (sem 10-11):** lanzamiento público open-source + Stripe billing + 5 clientes Pro firmados.

---

## Decisiones pendientes / open questions

| Tema | Pregunta | Cuándo resolver |
|---|---|---|
| ~~Tipografía~~ | ~~Proxima Nova o Inter~~ | ✅ **ADR-011: Inter free** |
| ~~Hosting backend~~ | ~~Coolify vs Fly vs Railway~~ | ✅ **ADR-012: Fly.io desde Cycle 2** |
| ~~Logo~~ | ~~Diseñar o usar Wordmark~~ | ✅ **ADR-013: Wordmark + Lucide hasta revenue** |
| ~~Test-psicometricos~~ | ~~Iframe o nativo~~ | ✅ **ADR-014: iframe en v0** |
| ~~Frontends hosting~~ | ~~Coolify vs Vercel~~ | ✅ **ADR-010: Vercel + subdominio default** |
| WhatsApp provider | 360dialog vs Twilio vs Meta direct | Cycle 2 |
| Cliente piloto pagado | Siete vs LinkedIn outbound frío | Cycle 1 cooldown |
| Open-source | Liberar Paperclip+OpenClaw+4 skills básicas | Cycle 4 |
| Dominio propio | Comprar `vortex-ops.com` o `vector-hr.tech` | Cooldown 4 (post-MRR target $1.5k) |

---

## Riesgos en watch (top 3)

1. **R-07 Bus factor 1.** Mitigación activa: docs obsesivas + repo público mes 4 (Cycle 4).
2. **R-15 Burnout.** Mitigación: respetar cooldown semana, no trabajar fines de semana.
3. **R-12 Vibe coding sin review.** Mitigación: DoD obligatorio + (futuro) code-review agent en CI.

---

## Métricas a empezar a medir desde Cycle 1

- Lead time (commit → prod) — auto-tracked por `nightly.yml`.
- Deploy frequency — auto-tracked.
- Eval pass rate por skill — `evals/runner.py` lo emite.
- Cost USD por run — sourcer/cv_evaluator ya devuelven `cost_usd` + breakdown; agregar Grafana panel en Cycle 2.
- Tiempo de pipeline HR (apply → score) — métrica de negocio principal.
