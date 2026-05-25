# 04 · Brand & Design System

## 1. Marca

**Vector HR Tech** opera **Vortex Ops**.

- **Personalidad:** Autoridad + Rebeldía + Jovialidad.
- **Slogan:** *"Hackeando la rutina, liberando el talento."*
- **Voz:** directa, sin jerga corporativa. Tutea. Usa "vamos a", "te toca", "listo".
- **Tono UI:** confianza tecnológica con un toque de irreverencia controlada.

## 2. Paleta primaria

| Token | Hex | RGB | HSL | Rol |
|---|---|---|---|---|
| `--vector-cian-dark` | `#1E1B4B` | `30, 27, 75` | `244, 47%, 20%` | Ancla / fondo principal / autoridad |
| `--vector-cian-electric` | `#00FFFF` | `0, 255, 255` | `180, 100%, 50%` | Tech / IA / acentos / data viz |
| `--vector-orange` | `#FF7F00` | `255, 127, 0` | `30, 100%, 50%` | CTA primario / rebeldía / jovialidad |
| `--vector-white` | `#FFFFFF` | `255, 255, 255` | `0, 0%, 100%` | Texto sobre dark / claridad |

## 3. Paleta secundaria (derivada)

Generada para escalas de UI completas (hover, disabled, error, success):

| Token | Hex | Uso |
|---|---|---|
| `--vector-cian-dark-50` | `#F5F5FA` | Background claro |
| `--vector-cian-dark-100` | `#E0DFEC` | Borders sutiles |
| `--vector-cian-dark-300` | `#7A77A8` | Texto secundario sobre fondo claro |
| `--vector-cian-dark-500` | `#1E1B4B` | **base** |
| `--vector-cian-dark-700` | `#15123A` | Hover de fondos oscuros |
| `--vector-cian-dark-900` | `#0A0824` | Sombras profundas |
| `--vector-orange-400` | `#FF9A33` | Hover CTA |
| `--vector-orange-600` | `#CC6600` | Active CTA |
| `--vector-cian-electric-200` | `#A6FFFF` | Glow sutil |
| `--vector-cian-electric-700` | `#00B8B8` | Acento sobre fondo claro |
| `--success` | `#10B981` | Validación correcta |
| `--warning` | `#F59E0B` | Atención |
| `--danger` | `#EF4444` | Error / destructivo |
| `--neutral-50..900` | escala gris | Texto, borders genéricos |

## 4. Tipografía

| Familia | Pesos | Uso | Fallback |
|---|---|---|---|
| **Proxima Nova** | Black, Bold, Semibold, Regular | Headers grandes (`<h1>`, `<h2>`), wordmark "VECTOR" | Inter, system-ui, sans-serif |
| **Lato** | Bold Italic, Bold, Regular, Italic | Eslogan, "HR TECH", micro-copy con energía | "Helvetica Neue", Arial |
| **JetBrains Mono** | Regular, Bold | Code blocks, IDs, números técnicos | ui-monospace, monospace |

**Escala** (mobile-first, rem, base 16):

| Token | rem | px | Uso |
|---|---|---|---|
| `--text-2xs` | 0.625 | 10 | Captions, labels técnicas |
| `--text-xs` | 0.75 | 12 | Labels, helper text |
| `--text-sm` | 0.875 | 14 | UI secundario |
| `--text-base` | 1 | 16 | Body |
| `--text-lg` | 1.125 | 18 | Body destacado |
| `--text-xl` | 1.25 | 20 | Section titles |
| `--text-2xl` | 1.5 | 24 | H3 |
| `--text-3xl` | 1.875 | 30 | H2 |
| `--text-4xl` | 2.25 | 36 | H1 mobile |
| `--text-6xl` | 3.75 | 60 | H1 hero desktop |

**Reglas:**
- Headers: Proxima Nova Black, tracking `-0.02em`.
- Body: Lato Regular, line-height `1.6`.
- "VORTEX OPS" como wordmark: Proxima Nova Black + Lato Bold Italic en "OPS".

## 5. Spacing, radii, shadows

```css
/* spacing scale (4px base) */
--space-0: 0;
--space-1: 0.25rem;  /* 4 */
--space-2: 0.5rem;   /* 8 */
--space-3: 0.75rem;  /* 12 */
--space-4: 1rem;     /* 16 */
--space-6: 1.5rem;   /* 24 */
--space-8: 2rem;     /* 32 */
--space-12: 3rem;    /* 48 */
--space-16: 4rem;    /* 64 */
--space-24: 6rem;    /* 96 */

/* radii */
--radius-sm: 0.25rem;
--radius-md: 0.5rem;     /* default */
--radius-lg: 0.75rem;
--radius-xl: 1rem;
--radius-full: 9999px;

/* shadows */
--shadow-sm: 0 1px 2px rgba(30, 27, 75, 0.05);
--shadow-md: 0 4px 12px rgba(30, 27, 75, 0.08);
--shadow-lg: 0 10px 30px rgba(30, 27, 75, 0.12);
--shadow-glow-cyan: 0 0 24px rgba(0, 255, 255, 0.4);   /* signature glow */
--shadow-glow-orange: 0 0 16px rgba(255, 127, 0, 0.35); /* CTA hover */
```

## 6. Componentes — reglas de uso

| Componente | Color base | Hover | Disabled | Notas |
|---|---|---|---|---|
| Button primary (CTA) | `--vector-orange` | `--vector-orange-400` + `--shadow-glow-orange` | opacity 50% | Texto blanco, peso bold |
| Button secondary | transparent + border `--vector-cian-electric` | bg `--vector-cian-electric/10` | — | Texto cian |
| Button ghost | transparent | bg `--vector-cian-dark/5` | — | Texto cian dark |
| Card (dark) | `--vector-cian-dark` | borde glow cyan | — | Hero/dashboard |
| Card (light) | `--vector-white` | shadow-md | — | Listados, formularios |
| Input | bg blanco, border neutral-200 | border `--vector-cian-electric` | bg neutral-50 | Focus ring 2px cian electric |
| Badge "AI" | bg cian electric, text dark | — | — | Para acciones de agentes |
| Badge "Manual" | bg neutral-100, text neutral-600 | — | — | Para acciones humanas |
| Toast success | bg green-500/10, border success, text success-700 | — | — | |
| Skeleton loader | gradient cian dark/5 → cian dark/10 (pulse) | — | — | |

**Modo dark = default** en cockpit HRBP y orgchart (autoridad + tech).
**Modo light = default** en career-site y candidate (cercanía + claridad).

## 7. Iconografía

- Librería base: **Lucide React** (mismo set que ya usas en `portal-de-talentos`).
- Tamaños: 16, 20, 24, 32 px.
- Stroke width: 1.75 (default lucide es 2; reducimos para look más fino y técnico).
- Color: heredado del texto.

## 8. Imagery / illustrations

- **Hero:** ilustraciones isométricas con fondos `--vector-cian-dark` y acentos `--vector-cian-electric` glow.
- **Avatares:** generación con DiceBear estilo "thumbs" o iniciales sobre `--vector-orange`.
- **Foto:** preferir gente real, alto contraste, post-procesada con leve tinte cian dark en sombras.
- **Patrones:** mesh gradient cian dark → cian electric muy sutil para fondos.

## 9. Motion

- **Easing default:** `cubic-bezier(0.16, 1, 0.3, 1)` (ease-out-quint, sensación de "snap").
- **Duración:** 150 ms (micro), 250 ms (transitions UI), 400 ms (page transitions).
- **Reducir movimiento:** respetar `prefers-reduced-motion`.
- **Signature animations:**
  - CTA hover: glow + leve scale 1.02.
  - Loader IA: shimmer cian electric sobre cian dark.
  - "Vibe" del agente trabajando: línea pulsante cian electric en barra de progreso.

## 10. Accesibilidad (no negociable)

- WCAG 2.2 **AA** mínimo, **AAA** en texto body.
- Contraste:
  - Texto sobre `--vector-cian-dark`: usar blanco (ratio > 12:1) ✓.
  - Texto sobre `--vector-orange`: usar **cian dark**, no blanco (orange + white falla AA en texto pequeño).
  - `--vector-cian-electric` solo para acentos grandes / iconos / shapes; **nunca para texto** sobre blanco (contraste insuficiente).
- Focus visible siempre (ring 2px cian electric con offset 2px).
- Soporte teclado completo en cockpit HRBP.
- Targets táctiles ≥ 44×44 px.
- `aria-label` y roles semánticos en todos los componentes interactivos.
- Testing con axe-core en CI (ver doc 06).

## 11. Tokens — implementación

Single source of truth: `packages/design-tokens/tokens.json` (formato Style Dictionary).

Build genera:
- `tokens.css` (custom properties)
- `tailwind.preset.js` (preset compartido)
- `tokens.ts` (TS types)
- `tokens.swift` / `tokens.kt` (futuro mobile)

```bash
pnpm --filter @vortex/design-tokens build
```

## 12. Wordmark y logo

```
VECTOR HR TECH
══════════════
[Proxima Nova Black]  [Lato Bold Italic]
   blanco / dark        naranja vibrante


VORTEX OPS
══════════
[Proxima Nova Black] [Lato Bold Italic]
   blanco / dark        cian electric
```

Variantes en `packages/design-tokens/assets/`:
- `logo-vector-hr-dark.svg` (sobre fondo claro)
- `logo-vector-hr-light.svg` (sobre fondo dark)
- `logo-vortex-ops-dark.svg`
- `logo-vortex-ops-light.svg`
- `favicon.svg` (V mark)
- `og-image.png` (1200×630 con slogan)

## 13. Inspiración (para alinear voz/visual)

| Marca | Qué tomamos |
|---|---|
| Linear | Layout denso, motion fina, dark por default |
| Vercel | Minimal + tipografía Geist tipo Proxima Nova |
| Stripe | Gradient sutil, accesibilidad, copy directo |
| Anthropic | Profesional pero no aburrido, claim corto |
| Apollo / Reply.io | UX denso para operadores expertos |

---

*Siguiente: [05 · Tech Stack & Best Practices](05_TECH_STACK_AND_BEST_PRACTICES.md)*
