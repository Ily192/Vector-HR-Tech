# 06 · Testing Strategy

## 1. Filosofía

> "Tests are how you sleep at night when you ship multiple times a day."

- **TDD donde la lógica es crítica** (workers HR/Sales, billing, RLS, run-token issuance).
- **Test-after donde es UI exploratoria.**
- **Pirámide invertida es anti-patrón:** menos E2E, más unit; pero E2E donde el flujo cruza ≥3 sistemas.
- **Para agentes, las pruebas son evals**, no asserts deterministas.

## 2. Pirámide

```
                ┌──────────────┐
                │     E2E      │  ~5%   Playwright + cliente real
                │  (smoke +    │
                │   golden)    │
                ├──────────────┤
                │ Integration  │  ~25%  pytest + testcontainers, MSW (frontend)
                ├──────────────┤
                │  Component   │  ~20%  Storybook + interaction tests
                ├──────────────┤
                │     Unit     │  ~50%  vitest, pytest
                └──────────────┘
```

## 3. Por capa

### 3.1 Unit tests

| Stack | Runner | Notas |
|---|---|---|
| TS frontend | **Vitest** + `@testing-library/react` | jsdom env; mock con `vi.mock` |
| TS shared packages | Vitest | Pure functions, schemas Zod |
| Python services | **pytest** + `pytest-asyncio` | Fixtures por proveedor |
| SQLAlchemy models | pytest + factory-boy | DB en memoria (sqlite) para casos triviales, Postgres real (testcontainers) para queries complejas |

**Coverage targets:**
- `services/control-plane`: ≥ 80%
- `services/hr-engine` y `sales-engine`: ≥ 70%
- `apps/*` críticos (forms, auth flows): ≥ 60%
- `packages/*`: ≥ 80%

### 3.2 Integration tests

| Caso | Tool |
|---|---|
| API + DB real | **pytest + testcontainers-python** (Postgres + Redis) |
| Frontend + API mockeada | **MSW (Mock Service Worker)** |
| Workers Celery | `pytest-celery` con eager mode |
| Supabase RLS | Tests directos contra DB con distintos JWT (ver §6) |
| Webhooks | `httpx.MockTransport` |

### 3.3 Component tests

- **Storybook 8** + `@storybook/test` (interaction tests).
- **Chromatic** o **Lost Pixel** para visual regression (free tier al inicio).
- Cada componente en `packages/ui` debe tener al menos 1 story por estado (default, loading, error, empty).

### 3.4 E2E tests

- **Playwright** con Chromium + WebKit + Firefox.
- 5-10 flujos críticos máximo (smoke):
  1. Candidato sube CV → recibe link de psicométrico → completa.
  2. HRBP login → ve pipeline → mueve candidato a "shortlist".
  3. HRBP crea vacante → agent sourcer arroja resultados.
  4. Onboarder genera constancia PDF correctamente.
  5. Multi-tenant: usuario empresa A no ve datos empresa B (test de RLS).
- **Trace siempre**, **video en fail**.
- En CI: `--shard=1/3` paralelizado.

### 3.5 Load / performance

- **k6** scripts en `tests/load/`.
- Targets:
  - 100 RPS sostenidos en `/api/career/*` con p95 < 300 ms.
  - Pipeline HR completo de 50 candidatos < 5 min wall-clock.
- Correr en cooldown de cada cycle (no en cada PR).

### 3.6 Accessibility

- **axe-core** vía `@axe-core/playwright` en E2E tests.
- **eslint-plugin-jsx-a11y** en lint (bloquea PR).
- Lighthouse CI con assertion `accessibility >= 95`.
- Auditoría manual con NVDA / VoiceOver una vez por mes.

### 3.7 Security tests

| Tipo | Tool | Frecuencia |
|---|---|---|
| SAST | **Semgrep** + reglas custom multi-tenant | Cada PR |
| Dependencies | **Dependabot** + **Snyk** | Diario |
| Secret scanning | **gitleaks** pre-commit + **GitHub secret scanning** | Cada commit |
| Container | **Trivy** sobre imágenes Docker | Cada release |
| DAST | **OWASP ZAP** baseline | Semanal en staging |
| RLS | Tests dedicados (ver §6) | Cada PR |

### 3.8 Contract tests

- **Pact** entre frontend y backend cuando crucemos equipos (futuro). Por ahora, **OpenAPI schema** generado por FastAPI + cliente TS auto-generado con `openapi-typescript` → contrato implícito.

## 4. Tests de agentes (evals)

> Los agentes son no-deterministas. `assertEquals` no aplica.

### 4.1 Estructura (formato gstack)

```
.agents/skills/<name>/evals/
├── golden_set.jsonl       Casos canónicos con expected behavior
├── regression_set.jsonl   Casos que rompimos en el pasado
├── adversarial.jsonl      Inputs maliciosos / edge
└── eval.config.yaml       Métricas + umbrales
```

### 4.2 Métricas por skill

| Skill | Métrica primaria | Umbral mínimo |
|---|---|---|
| `cv-evaluator` | Correlación score IA vs juicio humano (Pearson) sobre 100 CVs etiquetados | r ≥ 0.75 |
| `sourcer` | Recall@10 (cuántos de los top-10 humanos están en top-10 IA) | ≥ 0.7 |
| `psicometrico` | F1 contra etiquetas conductuales | ≥ 0.65 |
| `interviewer` | LLM-as-judge: relevancia + cobertura de preguntas críticas | ≥ 4/5 |
| `chro-intake` | Completitud de extracción JD/ICP/budget | 100% campos requeridos |
| `onboarder` | Output schema válido (Pydantic strict) | 100% pass rate |

### 4.3 Cuándo correr

- **Cada PR** que toca un `SKILL.md` o sus dependencias: corre `golden_set` + `regression_set`.
- **Nightly:** corre todo + `adversarial.jsonl`.
- **Semanal:** humano revisa muestras de outputs reales (drift detection).

### 4.4 Tooling

- Runner custom en `evals/runner/` que llama OpenAI/Gemini con el SKILL prompt + cada caso.
- LLM-as-judge cuando aplica (gpt-4o evalúa output con rúbrica).
- Resultados en `evals/results/<date>.json` + dashboard Grafana opcional.

## 5. Tests de RLS multi-tenant

**No negociable.** Una falla aquí = cliente exfiltra datos de otro.

```python
# tests/integration/test_rls.py
@pytest.mark.asyncio
async def test_candidato_aislamiento_entre_empresas(db, jwt_factory):
    empresa_a = await create_empresa(db, "A")
    empresa_b = await create_empresa(db, "B")

    candidato_a = await create_candidato(db, empresa_id=empresa_a.id)

    jwt_b = jwt_factory(empresa_id=empresa_b.id, role="HR")

    async with db_session_for_jwt(jwt_b) as session_b:
        result = await session_b.execute(
            select(Candidato).where(Candidato.id == candidato_a.id)
        )
        assert result.first() is None  # RLS bloquea
```

Cada tabla con `empresa_id` debe tener su test análogo. Generador en `scripts/gen_rls_tests.py`.

## 6. CI checklist (qué corre por PR)

```yaml
# Resumen del pipeline (detalle en doc 07)
on: [pull_request]
jobs:
  - lint (biome + ruff + markdownlint)
  - typecheck (tsc + mypy)
  - unit (vitest + pytest)
  - integration (testcontainers up)
  - rls-tests (Postgres + custom JWT)
  - eval-changed-skills (solo si .agents/skills/* cambió)
  - build (turbo build)
  - bundle-size-check (size-limit)
  - lighthouse-ci (en preview deploy)
  - playwright-smoke (en preview deploy)
  - semgrep
  - gitleaks
  - dependency-review
```

## 7. Datos de prueba

- **Fixtures estables** en `tests/fixtures/` (CVs anonimizados, JDs reales, transcripts).
- **factory-boy** (Python) y **fishery** (TS) para generar entidades.
- **Faker** con seed fijo en CI.
- **Anonimización:** scripts en `scripts/anonymize.py` para clonar prod → staging sin PII.

## 8. Mutation testing (futuro)

- **Stryker** (TS) y **mutmut** (Python) para validar calidad real de tests, no solo coverage.
- Correr mensualmente en cooldown.

## 9. Performance budgets en tests

| Métrica | Budget | Donde se mide |
|---|---|---|
| LCP | < 2.5 s | Lighthouse CI por PR |
| INP | < 200 ms | Lighthouse CI |
| CLS | < 0.1 | Lighthouse CI |
| API p95 | < 300 ms | k6 cooldown |
| Worker p95 | < 30 s | OTel trace |

PR rojo si excede budget.

## 10. Quién aprueba

- **Tests verdes ≠ aprobación.** Reviewer (humano o code-review agent) debe firmar.
- En PRs de docs only: auto-merge OK con CI verde.

---

*Siguiente: [07 · CI/CD & DevOps](07_CICD_AND_DEVOPS.md)*
