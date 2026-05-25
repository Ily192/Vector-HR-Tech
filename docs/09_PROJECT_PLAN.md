# 09 · Project Plan

> Roadmap detallado por cycles. Hitos claros, dependencias mapeadas, criterios de salida.

## 1. Visión a 12 meses

```
Q1 (sem 1-12):    MVP + 1 cliente piloto + 5 clientes Pro
Q2 (sem 13-24):   Sales-engine v1 + 10 clientes + Coolify hardening
Q3 (sem 25-36):   Skills cross-funcionales + 20 clientes + SOC 2 Type I prep
Q4 (sem 37-48):   Enterprise tier + SSO/SAML + 25 clientes + $20k MRR
```

## 2. Cycle 0 — Foundation (semana 0)

**Apetite:** 1 semana.
**Objetivo:** repo listo para que vibe coding empiece sin fricción.

### Entregables

- [x] Estructura monorepo creada (`apps/`, `services/`, `packages/`, etc.)
- [x] Documentación PMO (12 docs)
- [ ] Design tokens en `packages/design-tokens/tokens.json` + Tailwind preset
- [ ] CI workflows base (lint, typecheck, test stubs)
- [ ] `.env.example` + secrets en Doppler
- [ ] ADRs 001-008 escritas
- [ ] Submódulos / vendoring de paperclip-master + openclaw-main decidido (ADR-009)
- [ ] Repo en GitHub privado (luego público al final del cycle 1)

### Criterios de salida
- `pnpm install && pnpm dev` arranca apps con páginas placeholder en máquina limpia.
- CI verde en PR de prueba.
- Branch protection en `main` (require PR + status checks).

## 3. Cycle 1 — MVP HR Pipeline (semanas 1-2)

**Apetite:** 2 semanas. **Scope cuts permitidos:** WhatsApp (mover a cycle 2), psicométrico avanzado (queda básico).

### Pitch

> *Como HRBP, quiero subir una vacante y ver candidatos rankeados sin tocar n8n ni Excel, con un agente que me responda en Google Chat.*

### Hill chart objetivo

```
                   problem-solving         build           done
   sourcer worker      ● → → → → → → → → → → → ●
   cv-evaluator        ● → → → → → → → → → → → ●
   chro-intake skill                  ● → → → ●
   career-site MVP     ● → → → → → → → → → → → ●
   candidate portal    ● → → → → → → → → → ●
   hrbp cockpit              ● → → → → → → ●
   Paperclip+OpenClaw self-host ● → → → ●
```

### Tareas semana 1

| # | Tarea | Owner | Dependencia |
|---|---|---|---|
| 1.1 | Levantar Paperclip self-host en Coolify | Ilyra | infra |
| 1.2 | Levantar OpenClaw + adapter Google Chat | Ilyra | 1.1 |
| 1.3 | Migrar `HR proceso seleccion.json` → `hr-engine/workers/sourcer.py` | Vibe | DB schema |
| 1.4 | Migrar `Evaluador CV - subflujo.json` → `cv_evaluator.py` | Vibe | 1.3 |
| 1.5 | Schema Supabase + RLS + seed data | Ilyra | — |
| 1.6 | Diseñar wireframes career-site + candidate + hrbp en Figma | Ilyra | brand tokens |
| 1.7 | `packages/design-tokens` build | Vibe | brand |

### Tareas semana 2

| # | Tarea |
|---|---|
| 2.1 | Career-site: home + listado vacantes + detalle + apply form |
| 2.2 | Candidate: dashboard + status + test psicométrico embebido |
| 2.3 | HRBP cockpit: kanban pipeline + detalle candidato |
| 2.4 | Skill `chro-intake` (`SKILL.md` + eval golden set) |
| 2.5 | Skill `sourcer` |
| 2.6 | Skill `cv-evaluator` |
| 2.7 | Wire OpenClaw → hr-engine (run-token + tool gateway) |
| 2.8 | E2E test del flujo completo |

### Definition of Done Cycle 1

- ✅ Subir CV en career-site → ver score en hrbp en < 2 min wall-clock.
- ✅ Cobertura ≥ 60% en `services/hr-engine`.
- ✅ Lighthouse score ≥ 85 en career-site.
- ✅ RLS tests pasan.
- ✅ Loom demo público (5 min).

## 4. Cooldown 1 (semana 3)

- Refactor del `pipeline.py` orquestador.
- Mejorar evals del `cv-evaluator` (subir Pearson r de 0.6 → 0.75).
- Bug fixes de cliente alfa (Siete).
- Pitch del cycle 2.

## 5. Cycle 2 — Onboarding + Multi-canal + Sales-engine slim (semanas 4-5)

### Pitches candidatos

1. **HR onboarding completo:** scheduler + interviewer + onboarder + constancia generator.
2. **Multi-canal:** WhatsApp Business API + Telegram.
3. **Sales-engine slim:** integrar SDR-prospection multi-tenant.
4. **Org Chart Vortex:** UI mirror de Paperclip.

**Apuesta:** #1 + #2 (HR completo + WhatsApp). Sales y orgchart se quedan en backlog priorizado.

### Entregables

- Skills `interviewer`, `scheduler`, `onboarder`, `constancia_gen`, `compliance`.
- Adapter WhatsApp Business (proveedor: 360dialog o Twilio).
- Migration `Corrección de constancias.json` → `constancia_gen.py`.
- Migration `HR Crossboarding Talent.json` → `onboarder.py`.
- Test de carga: pipeline 50 candidatos < 5 min.

### DoD

- ✅ Cliente alfa procesa 50 candidatos reales en producción.
- ✅ Constancia PDF generada y firmada digitalmente.
- ✅ WhatsApp envía notificación al candidato cuando agendó entrevista.

## 6. Cooldown 2 (semana 6)

- Refresh staging desde prod anonimizado.
- Hardening seguridad: pen-test interno con OWASP ZAP.
- Documentación pública: blog post lanzamiento.
- Pitch cycle 3.

## 7. Cycle 3 — Sales-engine multi-tenant (semanas 7-8)

### Pitch

> *Cliente RPO necesita prospectar nuevos contratos mientras hace selección. Convertir SDR-prospection en módulo `sales-engine` integrado al control plane.*

### Entregables

- `services/sales-engine/` con todos los workers de SDR-prospection migrados a estructura Vortex (multi-tenant).
- Skills `hunter`, `outreach`, `closer`.
- UI: dashboard Sales en `apps/hrbp/sales/`.
- Bundle pricing Pro+ con Sales activo.

### DoD

- ✅ 1 campaña real corriendo para Siete (cliente alfa).
- ✅ Aislamiento entre tenants verificado en sales tables.

## 8. Cooldown 3 (semana 9)

- Caso de estudio Siete con números: tiempo ahorrado, candidatos procesados, revenue Sales.
- Pitch cycle 4.

## 9. Cycle 4 — Lanzamiento público + primeros 5 clientes Pro (semanas 10-11)

### Entregables

- Open-source de paperclip + openclaw + 4 skills básicas en GitHub público.
- Career site Vector HR Tech (`vector-hr.tech`) público con waitlist.
- Stripe billing integrado (Starter/Pro/Scale tiers).
- Onboarding self-served: form → tenant provisioning automático.
- Primeros 5 clientes Pro firmados (DM LinkedIn).

### DoD

- ✅ $1.5k MRR.
- ✅ Repo público con > 50 stars.
- ✅ NPS clientes ≥ 50.

## 10. Cooldown 4 (semana 12) → Cierre Q1

- Postmortem Q1.
- Roadmap Q2 escrito.
- Hire decision: ¿segundo dev?

## 11. Q2-Q4 — High-level

| Quarter | Foco principal | Hitos |
|---|---|---|
| Q2 | Skills cross-funcionales (Finance, Legal, IT, CS) | 10 clientes, $5k MRR, segundo dev (si aplica) |
| Q3 | Hardening Enterprise (SSO/SAML, audit log avanzado, helm chart K8s) | 20 clientes, $12k MRR, SOC 2 prep |
| Q4 | Marketplace de skills + 1 partner reseller LATAM | 25 clientes, $20k MRR, primer Enterprise |

## 12. Dependencias críticas (Critical Path)

```
brand tokens ──► UI components ──► apps frontends
        │
        └──► design system docs

Supabase schema ──► RLS tests ──► tenant_guard middleware ──► hr-engine workers
                                                        │
                                                        └──► OpenClaw skills
Paperclip self-host ──► run-token issuer ──► engines auth
```

Bloqueador potencial: si Supabase schema está mal, todo cae. **Schema review formal** antes de cycle 1 build.

## 13. Capacidad

- **1 dev FT** = ~30 horas productivas/semana (Ilyra).
- **Vibe coding** ~2-3x velocity en código repetitivo (workers, CRUDs, components).
- **Realistic throughput:** 1 cycle = ~60 horas humano + ~120 horas vibe-asistido.

## 14. Buffer y scope cuts

Reglas Shape Up clásicas:
- **Si vamos lentos al ~50% del cycle**, identificar **MVP del cycle** y cortar nice-to-haves.
- **No extender el cycle.** Mejor un cycle entregado al 80% que un cycle perpetuo al 100%.
- **Feature flags** para entregar a medias en producción si necesario (visible solo para staff).

## 15. Comunicación de progreso

- **Loom semanal** (viernes) para cliente alfa.
- **Hill chart actualizado** los viernes en `docs/specs/cycle-NN.md`.
- **Changelog público** auto-generado.
- **Status page** simple en `/status`.

---

*Siguiente: [10 · Risk Register](10_RISK_REGISTER.md)*
