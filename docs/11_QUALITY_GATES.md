# 11 · Quality Gates — Definition of Ready / Done

> Sin pasar el gate, no sigue. Sin excepciones de "para esta vez".

## 1. Definition of Ready (antes de empezar a codear)

### Para un pitch / cycle

- [ ] Pitch escrito en `docs/specs/cycle-NN.md` (problem, appetite, solution, no-gos).
- [ ] Hill chart inicial creado.
- [ ] Acceptance criteria explícitos y verificables.
- [ ] Dependencias identificadas (otras tareas, accesos, APIs).
- [ ] ADR escrita si la decisión arquitectónica es nueva.

### Para una tarea individual (PR)

- [ ] Issue / pitch ID enlazado.
- [ ] Approach descrito en 3-5 líneas.
- [ ] Riesgos identificados (`riesgo: …` en PR description).

## 2. Definition of Done — Por tipo de cambio

### 2.1 PR de código (general)

- [ ] **Lint verde** (biome / ruff / markdownlint).
- [ ] **Typecheck verde** (`tsc -b` / `mypy --strict`).
- [ ] **Tests unitarios** pasan; coverage no baja respecto a `main` (delta ≥ 0).
- [ ] **Tests de integración** pasan (con testcontainers Postgres+Redis).
- [ ] **Conventional Commit** title.
- [ ] **PR description** completo con checklist.
- [ ] **Reviewer** (humano o code-review agent) aprueba.
- [ ] **No `console.log` / `print` ni código comentado**.
- [ ] **No secretos** (gitleaks verde).
- [ ] **No `TODO`** sin link a issue.
- [ ] **Sin baja en bundle budget** (size-limit verde).
- [ ] **Sin baja en Lighthouse score > 5 puntos** en preview.

### 2.2 PR que toca DB schema

- [ ] **Migration generada con Alembic** + revisada a mano.
- [ ] **Down-migration escrita** (incluso si no se planea correr).
- [ ] **Patrón expand/contract** si rompería compatibilidad.
- [ ] **Dry-run en staging** ejecutado, output adjunto.
- [ ] **RLS policy** definida si tabla nueva tiene `empresa_id`.
- [ ] **Test de RLS** escrito y verde.
- [ ] **Índices justificados** (no agregar "por si acaso").

### 2.3 PR que toca un SKILL

- [ ] **`SKILL.md` actualizado** con nueva versión semver.
- [ ] **`agents/openai.yaml`** consistente con SKILL.
- [ ] **Eval suite golden + regression** corre y pasa umbral.
- [ ] **Diff del prompt** comentado en PR (qué cambió y por qué).
- [ ] **Costo estimado** del nuevo SKILL documentado (tokens promedio × precio).
- [ ] **Sin PII en fewshots**.

### 2.4 PR que toca UI

- [ ] **Componente en Storybook** con stories: default, loading, error, empty.
- [ ] **a11y axe-core**: 0 violations.
- [ ] **Visual regression**: aprobado en Chromatic / Lost Pixel.
- [ ] **Mobile** verificado (320px width mínimo).
- [ ] **Dark + light mode** OK.
- [ ] **Keyboard nav** verificado.
- [ ] **Reduced motion** respetado.
- [ ] **Screenshots** en PR (light + dark, mobile + desktop).

### 2.5 PR que toca seguridad / auth

- [ ] **Threat model actualizado** si la superficie cambia.
- [ ] **Tests de RBAC/ABAC** pasan.
- [ ] **Pen-test interno** corrido si es ruta pública nueva.
- [ ] **Aprobación adicional** de Ilyra (single approver overrideable solo aquí).

### 2.6 PR que toca CI/CD

- [ ] **Probado en branch fork** antes de mergear.
- [ ] **Tiempo total CI no sube > 30%** sin justificación.
- [ ] **Cache hit rate** documentado.

## 3. Quality gates en pipeline

```
┌─ pre-commit (husky) ─────────┐
│ - lint-staged                │
│ - gitleaks                   │
│ - commitlint                 │
└─────────────┬────────────────┘
              ▼
┌─ pre-push ───────────────────┐
│ - typecheck                  │
│ - tests cambiados            │
└─────────────┬────────────────┘
              ▼
┌─ CI por PR ──────────────────┐
│ - todo lo de pre-* + más:    │
│   integration, RLS, evals,   │
│   build, bundle-budget,      │
│   Lighthouse, Playwright,    │
│   semgrep, deps review       │
└─────────────┬────────────────┘
              ▼
┌─ Merge a main ───────────────┐
│ - all green required         │
│ - 1 reviewer required        │
│ - 0 unresolved comments      │
└─────────────┬────────────────┘
              ▼
┌─ Deploy staging (auto) ──────┐
│ - Playwright smoke           │
│ - Sentry health check        │
└─────────────┬────────────────┘
              ▼
┌─ Promote to prod (manual o  ─┐
│  canary 5% → 100%)           │
│ - 10 min monitor canary      │
│ - rollback automático si     │
│   error rate sube > 2x       │
└──────────────────────────────┘
```

## 4. Bypass

- **Hot fix Sev-1:** PR con label `hot-fix` puede saltar Lighthouse y Playwright (no lint/typecheck/RLS).
- **Docs only:** PRs que solo tocan `*.md` con CI verde pueden auto-merge sin reviewer.
- **Dependabot:** auto-merge si solo bumps minor/patch y CI verde.

## 5. Métricas de calidad continuas

| Métrica | Target | Alerta si |
|---|---|---|
| Coverage `services/control-plane` | ≥ 80% | baja > 5pp |
| Coverage `services/hr-engine` | ≥ 70% | baja > 5pp |
| Bundle size `apps/career-site` | < 150 KB gzip | > 175 |
| Lighthouse score | ≥ 90 | < 85 |
| Eval pass rate (skills) | ≥ 90% | < 80% |
| Test flakiness | < 1% | > 3% |
| MTTR | < 1 h | > 4 h |
| Change failure rate | < 15% | > 25% |

Reportadas semanalmente en `docs/runbooks/quality-report.md` (auto-PR).

## 6. Reglas de oro

> **Nunca** bypass por "luego lo arreglo".
> **Nunca** mergear con tests rojos esperando que "se arreglen solos".
> **Nunca** dos PRs simultáneos sin coordinación si tocan misma área.
> **Siempre** documentar la razón de cualquier deuda técnica reconocida (`docs/specs/tech-debt.md`).

---

*Siguiente: [12 · Observability](12_OBSERVABILITY.md)*
