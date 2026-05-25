# Postmortem — [Título corto del incidente]

- **Date:** YYYY-MM-DD
- **Severity:** Sev-1 / Sev-2 / Sev-3
- **Author:** Nombre
- **Status:** Draft / Reviewed / Published
- **Duration:** Xh Ym (detection → resolution)

## TL;DR

Una frase. Qué pasó, impacto, qué aprendimos.

## Impact

- Tenants afectados: X de Y.
- Usuarios afectados: ~Z.
- Datos afectados: <descripción, sin PII>.
- Revenue impact: $X.
- SLA impact: error budget consumido X%.

## Timeline

| Hora (UTC) | Evento |
|---|---|
| HH:MM | Cambio mergeado / deploy iniciado |
| HH:MM | Primera alerta |
| HH:MM | On-call detectó |
| HH:MM | Causa identificada |
| HH:MM | Mitigación iniciada |
| HH:MM | Servicio restaurado |
| HH:MM | All-clear |

## Root cause

Descripción técnica del *root cause* — no solo síntoma.

## Detection

- ¿Cómo se detectó? (alerta automática / cliente reportó / on-call vio dashboard)
- ¿Cuánto tardó la detección desde el inicio del impacto?
- ¿La alerta era accionable o requirió investigación adicional?

## Mitigation

- Pasos exactos tomados para resolver.
- ¿Hubo rollback? ¿feature flag? ¿hotfix?

## Lessons

**Lo que funcionó:**
- ...

**Lo que no funcionó:**
- ...

**Lo que tuvimos suerte de que funcionara:**
- ...

## Action items

> Cada uno con dueño y deadline. Tracked en GitHub issues.

| Prioridad | Acción | Dueño | Deadline | Issue |
|---|---|---|---|---|
| P0 | ... | @user | YYYY-MM-DD | #NN |
| P1 | ... | @user | YYYY-MM-DD | #NN |

## Blameless statement

Este postmortem es **blameless**: el foco es el sistema, no las personas. Los errores humanos son síntomas de gaps en herramientas, procesos o información disponibles.
