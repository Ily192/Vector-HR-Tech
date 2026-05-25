# 12 · Observability

> "If it's not measured, it's not running. If it's not alerted, it's already broken."

## 1. Pilares (los tres + uno)

| Pilar | Tool | Para qué |
|---|---|---|
| **Logs** | Better Stack (Logtail) o Grafana Loki | Búsqueda, debug, audit |
| **Metrics** | Prometheus + Grafana | Trends, capacity, business KPIs |
| **Traces** | OpenTelemetry → Honeycomb (free) o Tempo | Latencia, dependencies, root cause |
| **Errors** | Sentry | Stack traces, releases, regressions |
| **Sessions (UX)** | PostHog self-hosted | Funnels, feature flags, experiments |

## 2. Logs

### 2.1 Formato

JSON estructurado con campos estándar (todos los servicios):

```json
{
  "ts": "2026-05-08T15:30:00Z",
  "level": "info",
  "service": "hr-engine",
  "version": "2026.05.0",
  "env": "production",
  "trace_id": "abc123...",
  "span_id": "def456...",
  "empresa_id": "uuid",
  "run_id": "uuid",
  "agent_skill": "sourcer",
  "user_id": "uuid|null",
  "msg": "candidate scored",
  "candidate_id": "uuid",
  "score": 8.5,
  "cost_usd": 0.0042
}
```

### 2.2 Niveles

- `debug` — solo en local
- `info` — eventos de negocio normales
- `warn` — degradación recuperable
- `error` — fallo recuperable, ya manejado
- `critical` — paginar humano

### 2.3 Reglas

- **PII redacted antes de log:** emails, teléfonos, nombre completo → `<REDACTED>`.
- **No CV body, no transcript completo** en logs (link a storage S3 si necesario).
- **Sampling:** `info` 100% en dev, 100% en prod (volúmenes pequeños inicialmente). Bajar a 10% si > 10 GB/día.
- **Retention:** 30 días hot, 365 días cold (S3 + Athena).

## 3. Metrics

### 3.1 Categorías

| Categoría | Ejemplos |
|---|---|
| **RED (Request)** | rate, errors, duration por endpoint |
| **USE (Resources)** | CPU, RAM, disk, network |
| **SLO** | uptime, p95 latency, error budget |
| **Business** | candidatos procesados, vacantes activas, MRR, leads scored |
| **Cost** | $/run, $/skill, $/tenant |

### 3.2 SLOs (Service Level Objectives)

| Servicio | SLO | Window | Burn rate alert |
|---|---|---|---|
| career-site | 99.9% uptime, p95 < 500ms | 30d | 14.4x (1h) o 6x (6h) |
| candidate portal | 99.5% uptime, p95 < 800ms | 30d | 14.4x (1h) |
| hrbp cockpit | 99.5% uptime | 30d | 14.4x (1h) |
| hr-engine API | 99% uptime, p95 < 1s | 30d | 6x (6h) |
| hr-engine workers | 95% jobs success rate | 7d | error budget alert |
| control-plane | 99.9% uptime | 30d | 14.4x (1h) |

Error budget remaining < 20% → freeze de releases nuevas hasta recuperar.

### 3.3 Dashboards

Definidos en `infra/grafana/dashboards/`:

1. **Overview** — uptime, RPS, error rate, p95 todos los servicios.
2. **HR Engine Pipeline** — jobs/min por worker, success rate, queue depth.
3. **Tenant Cost** — $/empresa últimas 24h/7d/30d, top consumers.
4. **Skill Performance** — eval pass rate, drift score, latency por skill.
5. **Business** — funnel candidato (apply → score → shortlist → hire), MRR, churn.
6. **Infra** — VPS CPU/RAM, Postgres connections, Redis memory.

## 4. Traces

### 4.1 OpenTelemetry instrumentación

- **Auto-instrumentación** en FastAPI (`opentelemetry-instrumentation-fastapi`), SQLAlchemy, httpx, Celery, Redis.
- **Manual spans** en lógica crítica:
  ```python
  with tracer.start_as_current_span("sourcer.score_with_gemini") as span:
      span.set_attribute("empresa_id", str(empresa_id))
      span.set_attribute("candidate_count", len(candidates))
      ...
  ```
- **Trace context propagation** entre servicios (W3C trace context headers).

### 4.2 Sampling

- 100% en dev/staging.
- 10% en prod (suficiente para análisis estadístico, manejable en costo).
- 100% para errores (`always_on_error`).
- 100% para clientes Enterprise (debugging dedicado).

## 5. Errors (Sentry)

### 5.1 Configuración

- **Releases atadas a SHA** + auto source maps frontend.
- **User context:** `empresa_id`, `role`, `user_id` (sin email).
- **Breadcrumbs:** acciones recientes del usuario.
- **Performance monitoring:** habilitado, sample 10%.

### 5.2 Reglas de alertas Sentry

| Condición | Notificación | Sev |
|---|---|---|
| Nuevo issue P1 (excepción) | Telegram bot inmediato | Sev-1 |
| Issue regresa después de fix | Email | Sev-2 |
| Spike: > 10x error rate baseline en 5 min | Telegram bot + on-call | Sev-1 |
| Issue con tag `multi-tenant-leak` | Telegram bot inmediato | **Sev-1 crítico** |

## 6. Synthetic monitoring

| Endpoint | Cada | Desde | Alarma si |
|---|---|---|---|
| `/health` (todos) | 1 min | 3 regiones | 2 fails consecutivas |
| `/career-site` (carga page) | 5 min | LATAM | > 3s o status != 200 |
| Login flow simulado | 15 min | LATAM | falla |
| API E2E (apply → score) | 30 min | LATAM | > 30s o falla |

Tool: **Better Stack monitors** (free 10 monitors) o **UptimeRobot**.

## 7. Alerting

### 7.1 Canales

| Sev | Canal | Latencia objetivo |
|---|---|---|
| Sev-1 | Telegram bot personal + email | 1 min |
| Sev-2 | Telegram canal team | 15 min |
| Sev-3 | Email + Notion ticket | 1 día |
| Sev-4 | Slack `#vortex-noise` | best-effort |

### 7.2 Reglas obligatorias

- **No alarmas sin runbook.** Si no hay runbook en `docs/runbooks/incident-<id>.md`, la alarma es noise → bórrala o documéntala.
- **No spam.** Deduplicación 15 min default.
- **Alertas accionables**: deben incluir link al runbook + dashboard relevante.

## 8. Cost observability

Crítico porque LLMs y cloud escalan no linealmente.

### 8.1 Eventos `cost.consumed`

Cada llamada a LLM emite:

```json
{
  "event": "cost.consumed",
  "ts": "...",
  "empresa_id": "uuid",
  "service": "hr-engine",
  "agent_skill": "cv-evaluator",
  "provider": "gemini",
  "model": "gemini-1.5-flash",
  "tokens_in": 1234,
  "tokens_out": 567,
  "cost_usd": 0.0023,
  "run_id": "uuid"
}
```

### 8.2 Agregación

- Stream a tabla `cost_events` en Postgres (particionada por mes).
- Materialized view `tenant_monthly_spend` refrescada cada 5 min.
- Dashboard Grafana: gasto en vivo por empresa + ranking + alertas.

### 8.3 Hard-stops

- Paperclip lee `tenant_monthly_spend` antes de emitir run-token.
- Si tenant superó cap mensual → run-token denegado, agente notifica al HRBP.
- Override solo por SuperAdmin con justificación loggeada.

## 9. Audit log

- Tabla `activity_log` append-only.
- **Hash chain:** cada entrada incluye `prev_hash` → tampering detectable.
- **Retención: 365 días** (compliance LATAM).
- **Eventos auditados:**
  - login / logout
  - cambio de rol
  - acceso por SuperAdmin a datos de cliente
  - export de datos / borrado (GDPR-style)
  - cambio de configuración del tenant
  - aprobación de presupuesto / override
- **Inmutabilidad:** trigger en Postgres rechaza UPDATE/DELETE en `activity_log`.

## 10. Postmortems

- **Obligatorios para Sev-1 y Sev-2.**
- Plantilla en `docs/runbooks/postmortem-template.md`.
- Blameless: enfocado en sistema, no personas.
- Publicados (sin PII) en blog interno (mes 1) → blog público (mes 6+).

## 11. Reportes recurrentes

| Reporte | Frecuencia | Donde |
|---|---|---|
| DORA metrics | Semanal | `docs/runbooks/dora.md` (auto-PR) |
| Quality report (coverage, evals, flakiness) | Semanal | `docs/runbooks/quality-report.md` |
| Cost report por tenant | Diario para staff, mensual para cliente | dashboard + email PDF |
| Uptime SLO report | Mensual | `docs/runbooks/slo-report-YYYY-MM.md` |
| Risk register review | Por cooldown (cada 3 sem) | doc 10 actualizado |

## 12. Tooling stack final

```
                ┌──────────────────┐
                │  Frontend Apps   │
                └────────┬─────────┘
                         │ Sentry SDK + PostHog SDK + OTel browser
                         ▼
       ┌────────────────────────────────────┐
       │  OTel Collector (sidecar Coolify)  │
       └──┬───────────┬─────────┬───────────┘
          │ traces    │ logs    │ metrics
          ▼           ▼         ▼
       Honeycomb  BetterStack Prometheus
       (traces)   (logs)      ──► Grafana
                                  ──► AlertManager
                                       │
                                       ▼
                                 Telegram bot
                                 + Email
```

Costos estimados primer año: **< $50/mes** total (todo en free tier o casi).

---

*Fin de la documentación PMO. Volver a [00_README](00_README.md).*
