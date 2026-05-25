# 07 · CI/CD & DevOps

## 1. Principios

| # | Principio |
|---|---|
| 1 | `main` siempre desplegable. Cada commit en main → deploy a staging automático. |
| 2 | Trunk-based; branches < 2 días. |
| 3 | Feature flags > long-lived branches. |
| 4 | Deploy frecuente (≥ 1/día) baja MTTR (cambios pequeños = bugs aislables). |
| 5 | Rollback < 5 min siempre disponible. |
| 6 | Migrations zero-downtime (expand/contract). |

## 2. Entornos

| Entorno | Cuándo se despliega | URL pattern | Datos |
|---|---|---|---|
| `local` | dev en máquina | `http://localhost:*` | seed local |
| `preview` | por cada PR (Vercel + Coolify preview) | `https://pr-<n>-vortex.vercel.app` | snapshot anonimizado |
| `staging` | merge a `main` | `https://staging.vortex-ops.com` | clon prod anonimizado, refresh diario |
| `production` | tag `vX.Y.Z` o promote desde staging | `https://app.vortex-ops.com` | datos reales |

## 3. Pipelines (GitHub Actions)

### 3.1 `ci.yml` — por PR

```yaml
name: CI
on: [pull_request]
concurrency: { group: ci-${{ github.ref }}, cancel-in-progress: true }

jobs:
  lint:           # biome + ruff + markdownlint
  typecheck:      # tsc -b + mypy
  unit-ts:        # vitest --coverage
  unit-py:        # pytest --cov
  integration:    # testcontainers up (Postgres + Redis)
  rls-tests:      # tests dedicados multi-tenant
  evals:          # solo si .agents/skills/** cambió
  build:          # turbo build (cache S3)
  bundle-budget:  # size-limit
  semgrep:        # SAST
  gitleaks:       # secrets
  dependency-review: # dependabot
```

### 3.2 `preview-deploy.yml` — por PR

- Vercel deploy preview por cada `apps/*`.
- Coolify preview (docker compose) por cada `services/*` con label PR.
- Comment en PR con todas las URLs.
- Lighthouse CI corre en preview frontend.
- Playwright smoke corre contra preview.

### 3.3 `release.yml` — por merge a `main`

```yaml
on: { push: { branches: [main] } }
jobs:
  build-images:        # build & push Docker images con tag :sha
  deploy-staging:      # apply a Coolify staging
  smoke-staging:       # Playwright smoke
  promote-canary:      # 5% tráfico prod → nueva versión (feature flag)
  monitor-canary:      # 10 min watch Sentry/OTel
  promote-full:        # si métricas OK, 100%
```

### 3.4 `nightly.yml`

- Eval suite completa (golden + regression + adversarial).
- Refresh de staging desde dump anonimizado de prod.
- Reporte DORA → `docs/runbooks/dora.md` (auto-PR).

### 3.5 `scheduled-evals.yml`

- Lunes 9 AM: corre evals contra outputs reales de prod (sample 200 runs) → drift detection.

## 4. Build y artefactos

- **Imágenes Docker** firmadas con **cosign** y publicadas a GHCR.
- **Tags:** `:<sha>` (inmutable) + `:latest` (mutable, solo staging).
- **Multi-stage Dockerfiles** con caché de layers.
- **Distroless** para servicios Python (menos superficie de ataque).
- **SBOM** generado con `syft` en cada build, atado al artefacto.

## 5. Despliegue

### 5.1 Frontends

- **Vercel** (preview por PR + production por tag).
- ISR para `career-site`; SPA para `candidate` y `hrbp`.
- Edge config para feature flags.

### 5.2 Servicios backend

- **Coolify** sobre VPS (Hetzner CX31 o equivalente, ~$15/mes para start).
- Docker Compose declarativo en `infra/coolify/`.
- Healthchecks + auto-restart.
- TLS via Caddy (auto Let's Encrypt).
- Para Enterprise: helm chart Kubernetes en `infra/k8s/` (futuro).

### 5.3 Migrations

- **Expand/contract pattern:**
  1. Migration **expand** (agrega columnas/tablas, no rompe).
  2. Deploy app que escribe a ambos viejo+nuevo.
  3. Backfill data.
  4. Deploy app que lee solo nuevo.
  5. Migration **contract** (drop viejo).
- Cada migration corre **manualmente con dry-run** en staging primero.
- En producción: bloqueo de deploys nuevos hasta que migration termine (vía label en GitHub).

### 5.4 Secrets

- **GitHub Actions:** environment-scoped secrets.
- **Runtime:** **Doppler** (free tier) o **HashiCorp Vault dev** o env vars en Coolify.
- **Nunca** secretos en código, ni en Dockerfile, ni en `.env` versionado.
- `gitleaks` pre-commit + secret scanning GitHub.
- Rotación trimestral de keys (calendario Q en `docs/runbooks/rotation.md`).

## 6. Feature flags

- **Unleash** self-hosted (free) o **PostHog feature flags**.
- Tipos:
  - `release-flag` (release gradual, vida corta).
  - `experiment-flag` (A/B test).
  - `permission-flag` (por tenant/rol).
  - `kill-switch` (apagar feature en incidente).
- Cada flag tiene **fecha de eliminación** en su descripción. Auditoría mensual de flags huérfanos.

## 7. Monitoring & alerting

Detalle en doc 12. Pero CI/CD-relevante:

- **Sentry release tracking:** cada deploy etiqueta errores con su SHA.
- **OTel traces:** en cada deploy, dashboard de p95 latency baseline → si sube > 30%, alarma.
- **Synthetic checks** cada 1 min en `/health` de prod.

## 8. Rollback

| Tipo | Cómo | RTO |
|---|---|---|
| Frontend Vercel | Promote previous deployment | < 1 min |
| Backend Docker | `coolify rollback <service> --to <sha>` | < 5 min |
| Migration | Re-run down-migration (dry-run primero); si imposible, restore PITR | < 30 min |
| Datos | Supabase PITR (Point-In-Time Recovery, ventana 7 días en Pro) | < 30 min |

Runbook completo en `docs/runbooks/rollback.md`.

## 9. Backups y DR

| Activo | Backup | Frecuencia | Retención |
|---|---|---|---|
| Postgres | PITR Supabase | Continuo | 7 días Pro / 14 días Team |
| Postgres | Dump completo a S3-compatible (Backblaze B2 / Cloudflare R2) | Diario 03:00 UTC | 30 días |
| Storage (CVs, PDFs) | Replicación cross-region Supabase | — | — |
| Activity log | Append-only + dump diario | Diario | 365 días (compliance) |
| Secrets | Backup encriptado del vault | Semanal | 90 días |

**RPO objetivo:** 1 hora. **RTO objetivo:** 4 horas. **Test DR:** trimestral.

## 10. Versionado

- **Semver** en paquetes (`@vortex/ui`, `@vortex/types`).
- **CalVer** en producto (`vortex-ops-2026.05.0`).
- **Changesets** para auto-changelog y bumps.

## 11. Cost monitoring

- **Vercel:** alarma si gasto mensual > 110% del baseline.
- **Supabase:** alarma de uso de DB / storage / egress.
- **OpenAI / Gemini:** Paperclip emite eventos → dashboard Grafana de spend por tenant + alerta global.
- **Coolify VPS:** alarma de RAM > 85% sostenida 10 min.

## 12. On-call y escalación

- **PagerDuty** o **OpsGenie** (free tier) para Sev-1.
- **1 dev on-call** rotando si llegamos a 2 devs; mientras solo Ilyra: Telegram bot (`@vortex_oncall`) que escribe ante alertas Sentry P1.

| Severidad | Definición | Tiempo respuesta | Escalación |
|---|---|---|---|
| Sev-1 | Sistema caído / leak datos | 15 min | Inmediata |
| Sev-2 | Feature core degradada | 2 h | Hábil |
| Sev-3 | Feature secundaria | 1 día | Hábil |
| Sev-4 | Cosmético | Sprint | Cooldown |

Runbook por tipo de incidente en `docs/runbooks/incident-*.md`.

## 13. Métricas DORA (auto-tracked)

Script semanal `scripts/dora_metrics.py`:

| Métrica | Cómo se mide |
|---|---|
| Lead time | `git log` SHA primer commit → tag deploy |
| Deploy freq | count tags / día |
| Change failure rate | % deploys con rollback en 24h |
| MTTR | timestamp creación incidente Sentry → resolución |

Reporte en `docs/runbooks/dora.md`, auto-PR semanal.

## 14. Inspiración (cómo lo hacen los grandes)

| Empresa | Práctica que adoptamos |
|---|---|
| Stripe | API versioning + idempotency keys + cost tracking obsesivo |
| Vercel | Preview deploys por PR + edge config + Lighthouse CI obligatorio |
| GitHub | Trunk-based + feature flags + deploys cada 30min |
| Linear | Changesets + monorepo + Turbo cache + design tokens compartidos |
| Anthropic | Evals como tests de agente + cost cap por request |

---

*Siguiente: [08 · Security & Compliance](08_SECURITY_AND_COMPLIANCE.md)*
