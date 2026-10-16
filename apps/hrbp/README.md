# @vortex/hrbp

La app de la empresa: hoy es el cockpit del HR Business Partner. Es una SPA con Vite y React 19, desplegada en Vercel.

Producción: <https://vortex-hrbp.vercel.app>

> Con [ADR-017](../../docs/adr/017-career-site-modulo-gratuito.md) (Proposed) pasa a
> ser la app de cualquier empresa. Tendrá el módulo gratuito *Career site* (crear
> empleo, vacantes, aplicaciones) y, con el plan de pago, los servicios de IA.

## Cómo se corre

Desde la raíz del monorepo:

```bash
pnpm --filter @vortex/hrbp dev        # http://localhost:3001
pnpm --filter @vortex/hrbp test       # Vitest + Testing Library
pnpm --filter @vortex/hrbp build      # tsc -b + vite build
pnpm exec size-limit                  # el bundle principal tiene un tope de 90 KB (brotli)
```

## Estructura

```
src/
  App.tsx           el cockpit: solo presentación
  cockpit/
    resumen.ts      forma de los datos del cockpit y de dónde salen (hoy, ejemplo)
    embudo.ts       cálculos de dibujo del embudo (puros, con test)
  __tests__/
```

## Dónde van las reglas

Ver [ADR-016](../../docs/adr/016-logica-de-negocio-fuera-de-la-ui.md).

- **Indicadores** (conteos, variaciones, % del tope): los calcula el backend. `cockpit/resumen.ts` define la forma en que llegan; el componente no suma nada.
- **Etapas del embudo y su orden**: `ETAPAS_DEL_PIPELINE` de `@vortex/types/reglas`.
- **Textos de estados**: `@vortex/types/etiquetas`.
- **Importaciones**: se importa por subruta (`@vortex/types/reglas`, `/etiquetas`) y no desde la raíz, para no meter Zod en el bundle.
