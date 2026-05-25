# 03 · Architecture

> Vista C4 (System Context → Container → Component) + decisiones arquitectónicas clave.

## 1. Principios

| # | Principio | Implicación |
|---|---|---|
| 1 | **Multi-tenant nativo** | Cada query/RPC carga `empresa_id`; RLS en Supabase es la última línea de defensa. |
| 2 | **Governance > automation** | Toda acción debe pasar por Paperclip (presupuesto, aprobaciones, cuotas). Sin atajos. |
| 3 | **Channel-agnostic** | Lógica en backend, no en el canal. Cambiar WhatsApp → Telegram debe ser config. |
| 4 | **Skill-first, no prompt-spaghetti** | Cada agente es un `SKILL.md` versionado con evals. |
| 5 | **Self-hostable** | Una máquina + Docker compose levantan todo. Sin dependencias cloud propietarias. |
| 6 | **Type-safe end-to-end** | Zod schemas + TS types compartidos en `packages/types`; SQLAlchemy 2 + Pydantic v2 en backend. |
| 7 | **Async by default** | FastAPI async + Celery + WS. Nada bloqueante en la ruta del usuario. |
| 8 | **Vibe-codeable** | Estructura repetitiva por convención: copiar-pegar un worker es la forma natural de extender. |

## 2. Vista C4 — Nivel 1: System Context

```
        ┌──────────────┐         ┌──────────────┐
        │  Candidato   │         │    HRBP      │
        │  (web)       │         │  (web/chat)  │
        └──────┬───────┘         └──────┬───────┘
               │                        │
               ▼                        ▼
        ┌──────────────────────────────────────┐
        │           VORTEX OPS                 │
        │  (control + agents + engines + UI)   │
        └──┬──────────┬──────────┬─────────────┘
           │          │          │
   ┌───────▼──┐  ┌────▼────┐  ┌──▼─────────┐
   │ OpenAI / │  │WhatsApp │  │  Apollo /  │
   │ Gemini   │  │Telegram │  │ ZeroBounce │
   │ APIs     │  │GChat    │  │  Reply.io  │
   └──────────┘  └─────────┘  └────────────┘
```

## 3. Vista C4 — Nivel 2: Containers

```
┌────────────────── Frontends ────────────────────┐
│                                                  │
│  career-site         candidate         hrbp      │
│  (Next.js 14)       (Vite SPA)      (Vite SPA)   │
│        │                 │                │       │
└────────┼─────────────────┼────────────────┼──────┘
         │                 │                │
         │                 ▼                ▼
         │        ┌──────────────────────────────┐
         │        │  Supabase Edge Functions     │
         │        │  + Auth + Storage + Postgres │
         │        └──────────────┬───────────────┘
         │                       │
         ▼                       ▼
┌──────────────┐        ┌─────────────────┐
│ Career API   │        │  hr-engine      │
│ (Next.js     │        │  (FastAPI +     │
│  Route       │ ◄────► │   Celery)       │
│  Handlers)   │        │  Redis broker   │
└──────────────┘        └────────┬────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │  agent-plane    │
                        │  (OpenClaw      │
                        │   TS ESM)       │
                        └────────┬────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │ control-plane   │
                        │ (Paperclip      │
                        │  Node.js + PG)  │
                        └─────────────────┘
                                 │
                                 ▼
                         ┌────────────────┐
                         │  sales-engine  │
                         │  (FastAPI +    │
                         │   Celery)      │
                         └────────────────┘
```

## 4. Componentes clave

### 4.1 control-plane (Paperclip)

| Componente | Responsabilidad |
|---|---|
| Org chart service | CRUD de roles, agentes, jerarquías |
| Goals service | OKRs por empresa/rol/agente |
| Budget service | Hard-stops, alertas, billing por empresa |
| Heartbeats scheduler | Timer / on_demand / assignment / automation |
| Approvals workflow | Human-in-the-loop para acciones sensibles |
| Run-token issuer | JWT short-lived (5 min) por ejecución de agente |
| Activity log | Append-only, particionado por empresa, retención 365 días |

### 4.2 agent-plane (OpenClaw)

| Componente | Responsabilidad |
|---|---|
| Channel adapters | WhatsApp Business · Telegram · Slack · Google Chat · Teams · iMessage |
| Skill loader | Lee `.agents/skills/<name>/SKILL.md` + `agents/openai.yaml` |
| Conversation state | Per-thread context con TTL, persistido en Redis + Postgres |
| Tool gateway | Llama a HTTP endpoints de `hr-engine` / `sales-engine` con run-token |
| Plugin SDK | Extender canales o herramientas |

### 4.3 hr-engine

| Worker | Trigger | Output |
|---|---|---|
| `chro_intake` | webhook desde HRBP chat | Job + ICP + budget |
| `sourcer` | timer 6h o on-demand | candidatos_sourced |
| `cv_evaluator` | assignment (nuevo CV) | score + brechas |
| `psicometrico` | on_demand (link al candidato) | reporte conductual |
| `interviewer` | timer / event | resumen entrevista + score |
| `scheduler` | assignment | slots agendados (Google Calendar) |
| `onboarder` | timer 24h post-hire | constancia + welcome pack |
| `compliance` | timer semanal | reporte auditoría |

### 4.4 sales-engine (de SDR-prospection)

| Worker | Función |
|---|---|
| `pipeline` | Orquestador 70% DB Siete + 30% Apollo |
| `company_discovery` | Apollo company search |
| `company_context` | Web scraping + AI scoring |
| `contact_discovery` | Apollo people search |
| `contact_enrichment` | Email reveal |
| `email_validation` | ZeroBounce cascade |
| `data_validation` | Lead scoring |
| `reply_push` | Push paralelo a Reply.io |
| `campaign_scheduler` | Celery Beat cron |

### 4.5 frontends

| App | Framework | Deploy | Función |
|---|---|---|---|
| `career-site` | Next.js 14 (RSC + ISR) | Vercel | Landing pública, vacantes, SEO |
| `candidate` | Vite + React 18 SPA | Vercel | Portal del candidato (CV upload, tests, status) |
| `hrbp` | Vite + React 18 SPA | Vercel / Coolify | Cockpit del HR Business Partner |
| `orgchart` | Next.js 14 | Vercel | Visualización del Paperclip org chart en vivo |

## 5. Modelo de datos (núcleo)

```sql
-- Multi-tenant root
empresas (
  id uuid pk,
  name text,
  slug text unique,
  paperclip_company_id uuid,
  openclaw_workspace_id text,
  hr_engine_quota_monthly int default 1000,
  sales_engine_quota_monthly int default 500,
  color_primario text default '#1E1B4B',
  normativa_interna text,
  created_at timestamptz
)

-- HR domain
profiles (id uuid pk, empresa_id uuid fk, role enum, ...)
vacantes (id uuid pk, empresa_id uuid fk, jd text, icp_embedding vector(1536), ...)
candidatos (id uuid pk, empresa_id uuid fk, cv_url text, embedding vector(1536), ...)
applications (id uuid pk, vacante_id, candidato_id, score numeric, status enum, ...)
psicometricos (id uuid pk, application_id, report jsonb, ...)
entrevistas (id uuid pk, application_id, slot tstzrange, transcript text, ...)
constancias (id uuid pk, profile_id, type enum, pdf_url text, ...)

-- Sales domain
companies_master (id uuid pk, domain text unique, ...)
contacts_master (id uuid pk, email text unique, company_id uuid fk, ...)
icps (id uuid pk, empresa_id uuid fk, criteria jsonb, embedding vector(1536), ...)
campaigns (id uuid pk, empresa_id uuid fk, icp_id, prospect_quantity int, ...)
campaign_contacts (campaign_id, contact_id, status enum, ...)
prospecting_jobs (id uuid pk, campaign_id, status enum, ...)

-- Cross
runs (id uuid pk, empresa_id, agent_skill text, status enum, cost_usd numeric, ...)
activity_log (id bigserial, empresa_id, actor text, action text, payload jsonb, ts timestamptz)
budgets (empresa_id pk, monthly_cap_usd numeric, current_spend_usd numeric, ...)
```

**RLS:** todas las tablas con `empresa_id` tienen política `empresa_id = (auth.jwt() ->> 'empresa_id')::uuid`.

## 6. Flujo end-to-end (HR pipeline)

```
[Candidato sube CV en /career-site/[empresa]/[vacante]]
   │
   ▼
[Supabase storage + insert candidatos + trigger embedding job]
   │
   ▼
[hr-engine: cv_evaluator worker]
   ├─ Vector match contra vacante
   ├─ Gemini score 1-10 + brechas
   └─ INSERT applications (status='evaluated')
   │
   ▼
[Si score >= 7 → hr-engine: psicometrico worker]
   ├─ Genera link único /candidate/test/<token>
   └─ Notifica al candidato (OpenClaw → email/WhatsApp)
   │
   ▼
[Candidato completa test psicométrico]
   │
   ▼
[hr-engine: aplicación sube a status='shortlisted']
   │
   ▼
[OpenClaw scheduler skill: agenda con HRBP]
   │
   ▼
[HRBP entrevista → /hrbp marca decisión]
   │
   ▼
[Si HIRE → onboarder worker → constancia + accesos + welcome]
```

## 7. Decisiones arquitectónicas (ADRs)

Documentadas en `docs/adr/`:

| ID | Título | Estado |
|---|---|---|
| ADR-001 | Eliminar n8n; vibe-codear flows a FastAPI+Celery | Accepted |
| ADR-002 | Monorepo pnpm para frontends + packages, services Python independientes | Accepted |
| ADR-003 | Trunk-based development con feature flags | Accepted |
| ADR-004 | Supabase RLS como última línea de defensa multi-tenant | Accepted |
| ADR-005 | Paperclip emite run-tokens JWT 5 min; agentes nunca acceden directo a DB | Accepted |
| ADR-006 | Skill = `SKILL.md` + `agents/openai.yaml` (formato gstack/openclaw) | Accepted |
| ADR-007 | Pgvector en Supabase, no Pinecone (costo + lock-in) | Accepted |
| ADR-008 | Gemini 1.5 Flash como default para scoring; OpenAI gpt-4o solo para razonamiento complejo | Accepted |

## 8. Diagramas a producir

- [ ] C4 Context (Mermaid)
- [ ] C4 Container (Mermaid)
- [ ] C4 Component por servicio (Mermaid)
- [ ] ERD Supabase (dbdiagram.io export)
- [ ] Sequence: HR pipeline E2E (Mermaid)
- [ ] Sequence: agent run con run-token (Mermaid)

Todos en `docs/specs/diagrams/`.

---

*Siguiente: [04 · Brand & Design System](04_BRAND_AND_DESIGN_SYSTEM.md)*
