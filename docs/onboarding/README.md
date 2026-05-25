# Onboarding — Vortex Ops

Bienvenido. Esta guía te lleva de "repo recién clonado" a "primer commit verde" en ~30 minutos.

## 0. Prerrequisitos

Instalar (macOS/Linux/Windows con WSL2):

| Herramienta | Versión | Cómo |
|---|---|---|
| Node | ≥ 20 | `nvm install 20` |
| pnpm | ≥ 9 | `npm i -g pnpm@9` |
| Python | ≥ 3.12 | `pyenv install 3.12` |
| uv (Python deps) | ≥ 0.5 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Docker + Compose | latest | docker.com |
| Supabase CLI | ≥ 1.200 | `brew install supabase/tap/supabase` |

## 1. Clonar y arrancar dependencias locales

```bash
git clone <repo-url> vortex-ops
cd vortex-ops

# Postgres (con pgvector) + Redis vía docker-compose
docker compose -f infra/docker/docker-compose.dev.yml up -d

# Verificar que arrancaron sano
docker compose -f infra/docker/docker-compose.dev.yml ps
```

## 2. Variables de entorno

```bash
cp .env.example .env
# editar .env y completar OPENAI_API_KEY, GOOGLE_API_KEY, SUPABASE_*
```

Para `services/hr-engine` específicamente:
```bash
cp services/hr-engine/.env.example services/hr-engine/.env
```

## 3. Frontends + packages

```bash
pnpm install
pnpm tokens:build     # genera @vortex/design-tokens dist
pnpm dev              # arranca apps en paralelo (career-site:3000, hrbp:3001)
```

Abrir:
- http://localhost:3000 — career-site
- http://localhost:3001 — hrbp cockpit

## 4. Backend hr-engine

```bash
cd services/hr-engine
uv sync --dev

# en una terminal: API
uv run uvicorn app.main:app --reload --port 8000

# en otra: worker Celery
uv run celery -A app.workers.celery_app worker --loglevel=info --queues=hr
```

Probar:
```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

Docs interactiva: http://localhost:8000/docs

## 5. Aplicar schema Supabase (local)

Opción A — con Supabase CLI:
```bash
supabase init
supabase start
supabase db reset    # aplica migrations + seed
```

Opción B — directo a Postgres del compose:
```bash
psql postgresql://vortex:vortex@localhost:5432/vortex_dev \
  -f infra/supabase/migrations/0001_initial_schema.sql
psql postgresql://vortex:vortex@localhost:5432/vortex_dev \
  -f infra/supabase/seed.sql
```

## 6. Correr tests

```bash
# TS
pnpm test              # Vitest todos los packages
pnpm typecheck

# Python
cd services/hr-engine
uv run pytest tests/unit -v
uv run pytest tests/integration -v   # requiere docker compose up
```

## 7. Tu primer cambio

```bash
git checkout -b feat/onboarding-test
# Hacer un cambio menor (e.g. agregar tu nombre a docs/onboarding/contributors.md)
git add .
git commit -m "chore(onboarding): add <tu-nombre> to contributors"
git push -u origin feat/onboarding-test
gh pr create --fill
```

CI corre automáticamente. Cuando esté verde, mergear con squash.

## 8. Convenciones a recordar

- **Branches efímeros** (< 2 días).
- **Conventional Commits**: `feat(scope): ...`, `fix(scope): ...`.
- **Squash & merge** siempre.
- **DoD obligatorio** (ver `docs/11_QUALITY_GATES.md`).
- **Vibe coding declarado** en PR description (qué hizo Claude, qué hiciste tú).

## 9. Pidiendo ayuda

| Tema | Donde buscar primero |
|---|---|
| Arquitectura | `docs/03_ARCHITECTURE.md` |
| Stack y best practices | `docs/05_TECH_STACK_AND_BEST_PRACTICES.md` |
| Cómo correr tests | `docs/06_TESTING_STRATEGY.md` |
| Cómo deployar | `docs/07_CICD_AND_DEVOPS.md` + `docs/runbooks/deploy.md` |
| Diseño de un agente | `.agents/skills/sourcer/SKILL.md` (referencia) |
| Decisiones arquitectónicas | `docs/adr/` |

## 10. Siguiente

Lee el [Project Charter](../01_PROJECT_CHARTER.md) y la [Methodology](../02_METHODOLOGY.md) para entender el ritmo de trabajo (Shape Up + trunk-based).
