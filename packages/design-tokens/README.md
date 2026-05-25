# @vortex/design-tokens

> Single source of truth para la identidad visual de **Vector HR Tech / Vortex Ops**.

## Contenido

| Archivo | Para qué |
|---|---|
| `tokens.json` | Tokens crudos (Style Dictionary format) — fuente de verdad. |
| `tailwind.preset.js` | Preset Tailwind para todas las apps. |
| `theme.css` | Variables CSS para shadcn/ui (light + dark). |
| `dist/tokens.{js,d.ts,css}` | Generados por `pnpm build` (Style Dictionary). |

## Uso en una app

```ts
// tailwind.config.ts
import vortexPreset from "@vortex/design-tokens/tailwind.preset";

export default {
  presets: [vortexPreset],
  content: ["./src/**/*.{ts,tsx}"],
};
```

```ts
// app/layout.tsx (o main.tsx)
import "@vortex/design-tokens/theme.css";
```

## Paleta

| Token | Hex |
|---|---|
| `vector-cian-dark-500` | `#1E1B4B` |
| `vector-cian-electric-500` | `#00FFFF` |
| `vector-orange-500` | `#FF7F00` |
| `vector-white` | `#FFFFFF` |

Cada color tiene escala 50-900. Detalle en `tokens.json` y `docs/04_BRAND_AND_DESIGN_SYSTEM.md`.

## Tipografía

- **Display:** Proxima Nova (Black/Bold) — fallback: Inter, system-ui
- **Body:** Lato (Bold Italic / Regular) — fallback: Helvetica Neue, Arial
- **Mono:** JetBrains Mono

> Nota: Proxima Nova requiere licencia. Comprar antes de producción o sustituir por Inter.

## Build

```bash
pnpm --filter @vortex/design-tokens build
```

Genera `dist/` con outputs CSS/TS/JS para consumo en cualquier app.
