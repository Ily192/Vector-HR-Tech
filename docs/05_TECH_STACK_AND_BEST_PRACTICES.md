# 05 · Tech Stack & Best Practices

> Stack alineado con los líderes del mercado (Linear, Vercel, Stripe, Anthropic, Eightfold). No reinventar.

## 1. Frontend

### 1.1 Stack

| Capa | Elección | Versión | Por qué |
|---|---|---|---|
| Framework SSR | **Next.js 14** (App Router, RSC) | 14.2+ | Estándar de facto. RSC reduce JS al cliente. SEO nativo. Vercel deploy. |
| Framework SPA | **Vite + React 18** | 5.x / 18.x | Para portales internos no necesitamos SSR. HMR < 100 ms. |
| Lenguaje | **TypeScript 5.5+** strict | 5.5+ | `strict: true`, `noUncheckedIndexedAccess: true` |
| Styling | **Tailwind CSS 3.4** + design tokens | 3.4+ | Estándar industrial. Tokens en preset compartido. |
| UI primitives | **Radix UI** via **shadcn/ui** | latest | Headless + a11y. Linear y Vercel lo usan. |
| Forms | **React Hook Form** + **Zod** resolver | latest | Performance + validación tipada |
| Data fetching | **TanStack Query v5** | 5.x | Cache + revalidation; ya en `portal-de-talentos` |
| Server state | **TanStack Query** | — | (no Redux salvo state ultra-local) |
| Client state | **Zustand** | latest | Mínimo, sin boilerplate |
| Routing | App Router (Next) / **TanStack Router** (Vite) | latest | Type-safe routing |
| RPC | **tRPC v11** entre Next y Node services; REST FastAPI con OpenAPI auto | 11.x | End-to-end types |
| Realtime | **Supabase Realtime** + WS nativos | — | Pipeline updates al cockpit |
| Animations | **Framer Motion** v11 | 11.x | Para micro-interacciones del design system |
| Charts | **Recharts** (ya usado) | latest | Suficiente para dashboards |
| Tables | **TanStack Table v8** | 8.x | Headless, virtualización, server-side pagination |
| Icons | **Lucide React** | latest | Consistencia con repos existentes |

### 1.2 Best practices frontend

- **Server Components por default**, Client Components solo cuando necesitas state/effects/event handlers.
- **`use client` directive en hojas, no en raíces** (minimiza bundle cliente).
- **No `useEffect` para fetching** — usar TanStack Query o Server Components.
- **Streaming SSR + Suspense** boundaries por sección.
- **Image optimization:** `next/image` siempre, con `width`/`height`.
- **Fonts:** `next/font` (self-hosted Proxima Nova + Lato).
- **Bundle budget:** main bundle < 150 KB gzip. CI falla si excede.
- **Lighthouse score ≥ 90** en LCP, CLS, INP, TBT (medido por Vercel + Lighthouse CI).
- **a11y:** axe-core en CI, lint con `eslint-plugin-jsx-a11y`.
- **i18n preparado** desde día 1 (es-LATAM default, en como secundario).

### 1.3 Cómo lo hacen los grandes

- **Linear:** todo cliente-side state via Zustand + custom sync engine; trunk-based; design tokens compartidos via Stitches → Tailwind.
- **Vercel:** Next.js App Router + Turbopack + edge functions; design system Geist propio.
- **Stripe:** SSR + a11y AAA + telemetría performance en cada pageview; React, no fancy framework.

## 2. Backend (engines)

### 2.1 Stack

| Capa | Elección | Por qué |
|---|---|---|
| API framework | **FastAPI 0.110+** | Async nativo, OpenAPI auto, Pydantic v2 |
| ORM | **SQLAlchemy 2.0 async** + Alembic | Estándar Python; tipos correctos |
| Validación | **Pydantic v2** | Schemas runtime + IDE support |
| Task queue | **Celery 5** + Redis | Probado en `SDR-prospection`. `acks_late + reject_on_worker_lost` |
| Scheduler | **Celery Beat** | Heartbeats periódicos |
| Cache | **Redis 7** | Compartido con Celery broker |
| HTTP client | **httpx** async | Reemplaza `requests` (sync) |
| Lockfile | **uv** o **poetry** | uv preferido (10x más rápido) |
| Migrations | **Alembic** | Estándar SQLAlchemy |

### 2.2 Estructura por servicio (consistente)

```
services/<engine>/
├── app/
│   ├── __init__.py
│   ├── main.py              FastAPI app + middleware
│   ├── config.py            Pydantic Settings (env-driven)
│   ├── database.py          Async session factory
│   ├── monitoring.py        Sentry + OTel init
│   ├── api/                 Endpoints (router por dominio)
│   ├── models/              SQLAlchemy
│   ├── schemas/             Pydantic
│   ├── services/            Lógica de negocio (sin Celery)
│   ├── providers/           Adaptadores externos (OpenAI, WhatsApp, ...)
│   ├── workers/             Celery tasks (uno por archivo, patrón _run + task)
│   └── utils/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── alembic/
├── alembic.ini
├── pyproject.toml
├── Dockerfile
└── README.md
```

> **Convención sagrada:** cada `worker` tiene una función `async def _run(...)` que es testeable sin Celery, y un wrapper `@celery_app.task` que la llama. Esto viene de `SDR-prospection` y se mantiene.

### 2.3 Best practices backend

- **Async everywhere.** Routes async + httpx async + SQLAlchemy async + Celery 5 (con `asyncio.run` en task wrapper).
- **Settings tipadas** con Pydantic Settings. Sin `os.getenv` suelto.
- **Idempotencia obligatoria** en workers que llaman APIs externas (clave: `(empresa_id, run_id, step_name)`).
- **Retry policy explícito** con backoff exponencial. Distinguir errores transitorios vs permanentes.
- **Circuit breakers** (`pybreaker`) en providers externos.
- **Rate limiters** por proveedor (OpenAI, Apollo, ZeroBounce). Patrón `app/providers/rate_limiter.py` ya existente.
- **Logs estructurados** JSON con `structlog`. Campos obligatorios: `empresa_id`, `run_id`, `agent_skill`, `cost_usd`.
- **Cost accounting:** cada llamada a LLM emite evento → `runs.cost_usd` se actualiza → Paperclip checa hard-stop.
- **Migrations sin downtime:** zero-downtime patterns (expand/contract). Alembic genera, humano revisa antes de mergear.
- **Health endpoints:** `/health` (liveness) + `/ready` (DB + Redis check).

### 2.4 Cómo lo hacen los grandes

- **Stripe:** API versioning con header, idempotency keys por defecto, retries exponencial, observability obsesiva.
- **Anthropic:** evals como tests, tool calls con schemas, cost tracking por request.
- **Apollo / Reply.io:** Celery + Redis, rate limiters por API, dedup cross-pipeline.

## 3. Control plane (Paperclip)

- Mantener upstream `paperclip-master`. Submódulo o vendoring? **Submódulo Git** con tag pinned.
- Extender con plugins propios en `services/control-plane/plugins/vortex-multitenant/`.
- Custom adapter: `vortex-engine-http` (reemplaza n8n). Llama a `hr-engine` y `sales-engine` con run-token.

## 4. Agent plane (OpenClaw)

- **TS ESM strict** según `AGENTS.md` del repo.
- Skills viven en `.agents/skills/<name>/` siguiendo formato gstack:
  - `SKILL.md` — prompt, reglas, fewshots
  - `SKILL.md.tmpl` — variables `{{tenant}}`, `{{vacante_id}}`
  - `agents/openai.yaml` — display_name, short_description, default_prompt
  - `evals/` — eval cases (gstack pattern)
- Channels: empezar con **Google Chat** y **Telegram** (gratis, fácil); WhatsApp en cycle 2.

## 5. Database

| Capa | Elección |
|---|---|
| RDBMS | **Supabase Postgres 15** (managed). Self-host vía supabase-cli para clientes Enterprise. |
| Vector | **pgvector 0.7+** (no Pinecone) |
| Auth | Supabase Auth (JWT con custom claims `empresa_id`, `role`) |
| Storage | Supabase Storage (CVs, PDFs constancia, fotos) |
| RLS | **Obligatoria** en toda tabla con `empresa_id` |

### Best practices DB

- **Naming:** snake_case, plurales (`empresas`, `candidatos`).
- **PKs:** `uuid` con `gen_random_uuid()`, no serials.
- **Timestamps:** `created_at`, `updated_at` (`timestamptz`), trigger updated_at automático.
- **Soft deletes** vía `deleted_at` solo donde regulación lo exige; resto, hard delete con FK ON DELETE.
- **Índices:** crearlos cuando un query supera 100 ms. Monitorear via `pg_stat_statements`.
- **Particionamiento:** `activity_log` particionada por mes (retención 365 días).
- **Backups:** Supabase PITR + dump diario a S3-compatible (ver doc 08).

## 6. AI / LLMs

| Caso | Modelo | Por qué |
|---|---|---|
| Embedding (CV, JD, ICP) | OpenAI `text-embedding-3-small` (1536 dim) | Costo/calidad imbatible |
| Scoring rápido (CV fit, lead fit) | Google **Gemini 1.5 Flash** | $0.075/1M input — ~10x más barato que gpt-4o |
| Razonamiento complejo (entrevista, análisis psicométrico) | OpenAI **gpt-4o** | Calidad cuando importa |
| Conversación canal | OpenAI **gpt-4o-mini** o Gemini Flash | Latencia + costo |
| Function calling / tool use | gpt-4o (mejor adherencia a schemas) | |
| Code agents / SKILL.md | Claude (vía Cursor) | Vibe coding |

### Best practices LLM

- **Schemas estrictos** (Zod / Pydantic) para outputs estructurados; siempre `response_format: json_schema`.
- **Retries con backoff** + cap de tokens estricto.
- **Cost cap por run** desde Paperclip (denegar si excede).
- **Eval suite por skill** con fixtures versionadas (golden set + regression set).
- **Prompts versionados** en `SKILL.md` (git diff visible).
- **PII redaction** antes de loggear payloads de LLM.

## 7. DevEx (developer experience)

| Tool | Función |
|---|---|
| **pnpm 9** | Package manager monorepo (workspaces) |
| **uv** | Python deps + venvs (10x faster que pip) |
| **Turborepo** | Cache de tasks (build, lint, test) |
| **biome** | Lint + format JS/TS (reemplaza eslint+prettier en velocidad) |
| **ruff + black** | Lint + format Python |
| **commitlint + husky** | Conventional Commits enforcement pre-commit |
| **lint-staged** | Solo lintea lo cambiado |
| **changesets** | Versionado y changelogs auto en monorepo |
| **VSCode workspace settings** | `.vscode/settings.json` con format-on-save + extensiones recomendadas |

## 8. Convenciones de código

### TypeScript

- `strict: true`, `noUncheckedIndexedAccess: true`, `exactOptionalPropertyTypes: true`.
- No `any`. `unknown` + narrowing si necesario.
- Zod schemas como single source of truth: TS types se infieren de Zod.
- Imports absolutos con paths (`@vortex/ui`, `@vortex/types`).
- No barrel files masivos (rompen tree-shaking).

### Python

- Python 3.12+ con **type hints obligatorias** (mypy strict en CI).
- Pydantic v2 para validación.
- f-strings (no `.format`).
- Async-first; nunca mezclar sync DB calls con async route handlers.
- Imports ordenados con `ruff isort`.

### SQL

- Migrations en Alembic con `--autogenerate` pero **siempre revisadas a mano**.
- Una migration = una intención (no agrupar cambios no relacionados).
- Down-migrations escritas (aunque rara vez se corran).

## 9. Repositorio

- **Monorepo** vía **pnpm workspaces** + **Turborepo** para tasks de Node/TS.
- Servicios Python son sub-proyectos independientes con su propio `pyproject.toml` (no integrados a Turborepo, pero invocables vía `pnpm --filter`).
- Submodules para `paperclip-master` y `openclaw-main` (o vendoring si la extensión es invasiva — decisión en ADR-009).
- Conventional Commits + Changesets.
- README por cada paquete/servicio con `pnpm dev` runnable.

## 10. Observabilidad mínima

| Capa | Tool |
|---|---|
| Errores | **Sentry** (frontend + backend) |
| Logs | **Better Stack** (logs JSON estructurados, búsqueda) o **Grafana Loki** |
| Traces | **OpenTelemetry** + Honeycomb (free tier) o Grafana Tempo |
| Metrics | **Prometheus** + Grafana |
| Uptime | **Better Stack monitors** o **UptimeRobot** (gratis) |
| Sessions (UX) | **PostHog** self-hosted (eventos + feature flags + heatmaps) |

Detalle en [12_OBSERVABILITY.md](12_OBSERVABILITY.md).

---

*Siguiente: [06 · Testing Strategy](06_TESTING_STRATEGY.md)*
