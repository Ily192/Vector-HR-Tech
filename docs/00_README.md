# Vortex Ops — Documentación PMO

*Owner: Ilyra Rivas (Vector HR Tech)*
*PMO: Claude Opus 4.7 (asesor)*
*Última actualización: 2026-05-08*

## Cómo leer este pack

Doce documentos numerados, cada uno responde una pregunta del PMO senior:

| # | Doc | Pregunta que responde |
|---|---|---|
| 01 | [Project Charter](01_PROJECT_CHARTER.md) | ¿Qué construimos, para quién, por qué, con qué éxito? |
| 02 | [Methodology](02_METHODOLOGY.md) | ¿Cómo trabajamos? (ciclo, sprints, ceremonias) |
| 03 | [Architecture](03_ARCHITECTURE.md) | ¿Cómo se ven el sistema y los datos? |
| 04 | [Brand & Design System](04_BRAND_AND_DESIGN_SYSTEM.md) | ¿Cómo se ve y se siente? |
| 05 | [Tech Stack & Best Practices](05_TECH_STACK_AND_BEST_PRACTICES.md) | ¿Qué herramientas usamos y cómo, alineados con los grandes? |
| 06 | [Testing Strategy](06_TESTING_STRATEGY.md) | ¿Cómo garantizamos calidad? (pirámide, evals, contratos) |
| 07 | [CI/CD & DevOps](07_CICD_AND_DEVOPS.md) | ¿Cómo integramos y desplegamos? |
| 08 | [Security & Compliance](08_SECURITY_AND_COMPLIANCE.md) | ¿Cómo protegemos datos y cumplimos? |
| 09 | [Project Plan](09_PROJECT_PLAN.md) | ¿Qué hacemos cuándo? (timeline, hitos, dependencias) |
| 10 | [Risk Register](10_RISK_REGISTER.md) | ¿Qué puede salir mal y cómo lo mitigamos? |
| 11 | [Quality Gates](11_QUALITY_GATES.md) | ¿Cuándo decimos que algo está "Done"? |
| 12 | [Observability](12_OBSERVABILITY.md) | ¿Cómo sabemos qué pasa en producción? |

## Estado del proyecto

- **Fase actual:** Discovery → Foundation (semana 0)
- **Hito próximo:** MVP Cycle 1 — fin de semana 2
- **Modo de ejecución:** Shape Up adaptado, 2-week cycles, 1-week cooldown
- **Equipo:** 1 dev FT (Ilyra) + Claude/Cursor (vibe coding)
- **Repos satélite leídos:** `paperclip-master`, `openclaw-main`, `gstack-main`, `SDR-prospection`, `portal-de-talentos-main`, `Portal-HR-TH-main`, `Test-psicometricos-main`, `brochure-talent-main`

## Decisiones ya tomadas

- ADR-001: n8n eliminado, lógica vibe-codeada a FastAPI + Celery (ver `adr/001-no-n8n.md` cuando se cree).
- ADR-002: Monorepo pnpm + workspaces para frontends/packages; servicios Python como sub-proyectos independientes con su propio `pyproject.toml`.
- ADR-003: Trunk-based development con feature flags. Sin gitflow.
- ADR-004: Todo PR debe pasar lint + typecheck + tests + (en agentes) evals.

## Convenciones del repo

- **Branching:** `main` siempre desplegable. Branches efímeros `feat/<scope>-<short>`, `fix/<scope>-<short>`, `chore/<scope>-<short>`.
- **Commits:** Conventional Commits (`feat(hr-engine): add sourcer worker`).
- **PRs:** plantilla obligatoria, mínimo 1 reviewer (o auto-merge si solo cambia docs/tests y CI verde).
- **Idioma:** código y commits en inglés; docs de producto y comunicación con cliente en español.
- **Auto-format:** prettier + biome (TS/JS) · ruff + black (Python) · markdownlint (docs).

---

*Lee primero el [Project Charter](01_PROJECT_CHARTER.md) si vienes de cero.*
