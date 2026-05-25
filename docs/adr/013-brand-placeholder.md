# ADR-013 · Brand placeholder: Wordmark + Lucide hasta revenue

- **Status:** Accepted
- **Fecha:** 2026-05-25
- **Decisores:** Ilyra

## Contexto

El brand spec (`04_BRAND_AND_DESIGN_SYSTEM.md`) deja abierto el logo. Diseñar uno propio cuesta $500-2k con un freelance LATAM o $50-150 con un AI tool + iteración. Antes de tener revenue es difícil justificar.

## Decisión

**v0 (Cycle 0-4): no diseñamos logo. Brand visual = Wordmark text-based + iconografía de Lucide.**

- `<Wordmark brand="vortex" />` y `<Wordmark brand="vector" />` ya implementados en `packages/ui/src/wordmark.tsx`.
- Para íconos contextuales usamos [Lucide React](https://lucide.dev) (MIT, ~1000 íconos vectoriales).
- El "logo" en favicon es la letra V cyan-electric sobre cian-dark, generada con Inter Black + glow CSS.

**Re-evaluación:** Cycle 4 (lanzamiento público). Si NPS de clientes Pro ≥ 50, invertir en logo propio.

## Consecuencias

### Positivas

- Cero costo creativo durante MVP. Cero bloqueador.
- Wordmark + Lucide es estética válida y moderna (Linear, Vercel, Resend usan este patrón).
- Cuando se decida logo, swap es 1 archivo (`wordmark.tsx`) + favicon.

### Negativas

- Menos memorable que un logo bien diseñado. Aceptamos para v0.

## Acciones

- [x] Wordmark ya existe en `packages/ui/src/wordmark.tsx`.
- [ ] Generar favicon V cyan en SVG y agregarlo a `apps/career-site/public/` y `apps/hrbp/public/` — pendiente próxima sesión.
- [ ] Cycle 4 Cooldown: decidir si invertir en logo propio.
