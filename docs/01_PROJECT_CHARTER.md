# 01 · Project Charter

## 1. Visión

Construir el **Operations Engine** open-core, agentic y multi-tenant que LATAM no tiene: una sola plataforma donde agentes autónomos ejecutan HR + Sales + Cross-functional ops, gobernados por presupuesto y org chart, conversando con humanos por los canales que ya usan (WhatsApp first).

## 2. Misión

Eliminar la rutina operativa de las consultoras HR / RPO / staffing firms / holdings, liberando el talento humano para hacer el trabajo cognitivo que sí importa.

## 3. Objetivos SMART (12 meses)

| ID | Objetivo | Métrica | Fecha |
|---|---|---|---|
| O1 | MVP self-host listo y desplegado en Coolify | repo público + Loom demo | sem 4 |
| O2 | 1 cliente piloto en producción (Siete o externo) | NPS ≥ 50 + retención > 90 días | mes 3 |
| O3 | 10 clientes Pro de pago | $5k MRR | mes 6 |
| O4 | Break-even operativo | $4.5k MRR cubre OPEX | mes 6 |
| O5 | 25 clientes (mix Pro + Scale + 1 Enterprise) | $20k MRR | mes 12 |

## 4. Alcance

### 4.1 Dentro de alcance (MVP, semanas 1-4)

- Control plane (Paperclip self-hosted) con multi-tenant via tabla `empresas`.
- Agent plane (OpenClaw) con 2 canales: Google Chat + Telegram (WhatsApp en cycle 2).
- 6 SKILL.md HR: `chro-intake`, `sourcer`, `cv-evaluator`, `psicometrico`, `interviewer`, `onboarder`.
- HR-engine con 6 workers Celery (uno por skill).
- Frontend mínimo: career-site público + portal candidato + cockpit HRBP.
- Integración del repo `Test-psicometricos` como ruta dentro de candidate.
- CI/CD básico (lint + typecheck + tests + deploy a Coolify).
- Observability: Sentry + logs estructurados.

### 4.2 Fuera de alcance (MVP)

- Sales-engine completo (queda en cycle 2; el repo SDR-prospection ya existe).
- Skills cross-funcionales (Finance, Legal, IT) — cycle 3.
- Integraciones SAML/SSO empresariales — cycle 4 (Enterprise tier).
- Marketplace de skills de terceros — backlog.
- Mobile apps nativas — backlog.
- On-prem deployment con air-gap — solo Enterprise bajo demanda.

## 5. Stakeholders

| Rol | Quién | Responsabilidad |
|---|---|---|
| Sponsor / Product Owner | Ilyra Rivas | Decisiones de producto y comerciales |
| Tech Lead / FT Dev | Ilyra Rivas | Implementación |
| Vibe-coding partner | Claude / Cursor | Pair programming, scaffolding |
| Cliente alfa | Siete (consultora propia) | Validación de procesos HR reales |
| Cliente piloto pagado | TBD (RPO LATAM) | Primer revenue + case study |
| Asesor PMO | Claude Opus 4.7 | Planning, métricas, riesgos |

## 6. Beneficios y casos de negocio

| Para el cliente | Para Vector HR Tech |
|---|---|
| Reducción 60-80% en tiempo de selección | ARR recurrente con margen 84% |
| Multi-canal sin pagar 5 herramientas | Cross-sell HR ↔ Sales ↔ Cross |
| Gobierno y auditoría built-in | Open core → comunidad → leads |
| Self-host (sin vendor lock-in) | Ecosistema de skills (marketplace futuro) |

## 7. Restricciones y supuestos

**Restricciones:**
- 1 dev full-time durante los primeros 6 meses.
- Presupuesto infra inicial < $200/mes (Coolify VPS + Supabase Pro + APIs IA).
- LATAM-first: español, WhatsApp, horarios GMT-3 a GMT-6.

**Supuestos:**
- Paperclip y OpenClaw mantienen API estable (versionado + tests CI mitigan).
- Supabase Pro suficiente hasta ~50 tenants activos.
- Cliente alfa (Siete) acepta ser conejillo de indias.

## 8. Criterios de éxito (Definition of Done del proyecto)

El proyecto **se considera entregado** cuando:

1. ✅ MVP corriendo 24/7 en Coolify VPS con uptime > 99%.
2. ✅ Cliente piloto procesa ≥ 50 candidatos reales sin intervención manual.
3. ✅ NPS del cliente piloto ≥ 50.
4. ✅ Documentación completa publicada en `docs/`.
5. ✅ Repo público con README + Loom demo + `pnpm install && pnpm dev` funcionando en máquina limpia.
6. ✅ Test coverage ≥ 70% en `services/hr-engine` y `services/control-plane`; ≥ 60% en frontend.
7. ✅ DORA: lead time < 1 día, deploy freq diario, MTTR < 1 hora, change failure rate < 15%.

## 9. Riesgos top-3

Detallados en [10_RISK_REGISTER.md](10_RISK_REGISTER.md).

1. **Breaking changes de Paperclip / OpenClaw upstream.** Mitigación: pin versión + fork si necesario.
2. **Costo de tokens de IA explota con primer cliente activo.** Mitigación: budget hard-stops nativos en Paperclip, alarmas Sentry.
3. **No conseguir cliente piloto pagado en mes 3.** Mitigación: usar Siete como producto interno (case study self-served).

## 10. Aprobación

| Rol | Nombre | Aprobado |
|---|---|---|
| Sponsor | Ilyra Rivas | ⏳ pendiente |
| PMO | Claude Opus 4.7 | ✅ 2026-05-08 |

---

*Siguiente: [02 · Methodology](02_METHODOLOGY.md)*
