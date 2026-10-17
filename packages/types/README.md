# @vortex/types

Tipos, esquemas Zod y reglas espejadas que comparten los frontends. Su contraparte en Python es el hr-engine.

## Contenido

| Subruta | Qué tiene |
|---|---|
| `@vortex/types/hr` | Esquemas de vacante, candidato, aplicación, salida de `cv-evaluator` y `VacantePublica` (la fila de la vista pública) |
| `@vortex/types/tenant` | Empresa, perfiles, roles y claims del JWT (ADR-015) |
| `@vortex/types/sales` | Dominio del sales-engine |
| `@vortex/types/reglas` | Reglas del backend que la UI muestra: `siguientePaso`, `UMBRALES_SIGUIENTE_PASO`, `ETAPAS_DEL_PIPELINE` |
| `@vortex/types/etiquetas` | Texto en español de cada enum |

`@vortex/types` (la raíz) reexporta todo. En el bundle de una SPA conviene importar por subruta: `reglas` y `etiquetas` no cargan Zod.

## Contratos con el backend

Cada esquema o regla que existe en los dos lenguajes tiene un JSON en `contracts/`, y lo prueban los dos lados:

| Contrato | Dueña (Python) | Test TS | Test Python |
|---|---|---|---|
| `cv-evaluation.json` | `app/clients/scoring.py::CvEvaluation` | `contrato-cv-evaluation.test.ts` | `test_contrato_cv_evaluation.py` |
| `siguiente-paso.json` | `app/domain/siguiente_paso.py` | `reglas.test.ts` | `test_contrato_siguiente_paso.py` |

Si cambias un límite o un umbral, cámbialo en el contrato y en los dos lados en el mismo PR.

## Reglas para añadir algo aquí

- Solo entra lo que usan dos o más apps, o lo que espeja al backend.
- Una regla espejada no decide nada en la UI: sirve para mostrar o anticipar lo que hará el backend ([ADR-016](../../docs/adr/016-logica-de-negocio-fuera-de-la-ui.md)).
- Todo lo que se exporta lleva TSDoc: qué es y quién es la dueña.

```bash
pnpm --filter @vortex/types test
pnpm --filter @vortex/types typecheck
```
