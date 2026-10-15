# @vortex/design-tokens

> Single source of truth para la identidad visual de **Vector HR Tech / Vortex Ops**.

## Contenido

| Archivo | Para qué |
|---|---|
| `tokens.json` | Tokens crudos (Style Dictionary format) — fuente de verdad. |
| `tailwind.preset.js` | Preset Tailwind para todas las apps. |
| `theme.css` | Variables CSS para shadcn/ui (light + dark), marca v1. |
| `brand-v2.css` | Marca v2 (color, tipografía y escala de riesgo) como variables CSS. Ver `docs/brand/branding-v2.md`. |
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

## Paleta (marca v2)

| Clase Tailwind | Hex | Uso |
|---|---|---|
| `ink-900` | `#181854` | Texto, superficies oscuras, botón `ink` |
| `flame-500` | `#FE7802` | CTA (texto en `ink-900`) |
| `aqua-300` / `aqua-700` | `#3EECEB` / `#066263` | Acento sobre tinta / enlaces sobre claro |
| `mist-50` · `mist-200` · `mist-600` | `#F7F8FC` · `#DBDDE8` · `#686B78` | Fondo · bordes · texto secundario |
| `risk-{nulo,bajo,medio,alto,muy-alto}` | ver guía | Semáforos (relleno + `.text`) |

Utilidades: `bg-brand-gradient`, `shadow-soft|lift|float|cta`, `.eyebrow` y `.brand-underline` (en `theme.css`). Tipografía: Figtree vía `--font-sans` y JetBrains Mono vía `--font-mono`. La paleta `vector-*` (v1) sigue en `tokens.json` pero está en desuso. Guía completa: `docs/brand/branding-v2.md`.
