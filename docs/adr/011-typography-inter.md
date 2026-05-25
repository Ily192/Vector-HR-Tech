# ADR-011 · Tipografía: Inter como display + Lato como body (free)

- **Status:** Accepted
- **Fecha:** 2026-05-25
- **Decisores:** Ilyra
- **Supersedes:** Decisión pendiente en `04_BRAND_AND_DESIGN_SYSTEM.md`

## Contexto

El brand spec original (`docs/04_BRAND_AND_DESIGN_SYSTEM.md`) define **Proxima Nova** como font display (headers + wordmark "VECTOR") y **Lato** como body. Proxima Nova es una licencia paga (~$300-500 USD/dominio) y bloquea el Cycle 1 wk2.

Restricciones:

- No tenemos revenue todavía. Comprar licencia hoy es prematuro.
- El branding ya está expresado en color + voice; la diferencia tipográfica es secundaria.
- Inter tiene la misma vibe geometric-sans que Proxima Nova y soporta el peso `black` (900) que necesita el wordmark.
- Lato es free en Google Fonts.

## Decisión

**v0 (Cycle 0-4): Inter (display) + Lato (body). Ambas vía Google Fonts.**

- `tokens.json` actualizado: `font.family.display = "Inter, system-ui, sans-serif"`.
- `font.family.body = "Lato, 'Helvetica Neue', Arial, sans-serif"` (sin cambios).
- Pesos cargados: Inter 400/600/700/900, Lato 400/700.
- `<link>` preconnect a fonts.googleapis.com en cada app.

**Re-evaluación:** Cooldown 4 (semana 12). Si la diferencia visual entre Inter y Proxima Nova se nota lo suficiente como para afectar percepción de marca con clientes Pro pagados, se compra la licencia.

## Consecuencias

### Positivas

- Cero costo. Cero bloqueador para arrancar Cycle 1 wk2.
- Inter Variable Font es UN solo archivo para todos los pesos — bundle size mínimo.
- Lato + Inter es una combinación validada por sistemas como Mailchimp, Linear (early), GitHub Primer.

### Negativas / Trade-offs

- Inter no tiene exactamente la misma "rebeldía geométrica" de Proxima Nova en el wordmark. Aceptamos para v0.
- Cuando se compre Proxima Nova hay que renombrar variables CSS + actualizar tokens — esfuerzo bajo (10 min) porque está centralizado en `tokens.json`.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Comprar Proxima Nova ahora | Prematuro pre-revenue. |
| Solo Inter (sin Lato) | Pierde el dual personality que el brand spec define (autoridad / jovialidad). |
| Manrope o Plus Jakarta Sans | Otras alternativas free a Proxima Nova. Inter ganó por adoption + variable font support. |
| Self-host woff2 desde Bunny Fonts | Optimización prematura — Google Fonts con preconnect es suficiente para Lighthouse 85+. |

## Acciones

- [x] Actualizar `packages/design-tokens/tokens.json`.
- [ ] Verificar que `apps/career-site/src/app/layout.tsx` y `apps/hrbp/index.html` cargan Inter+Lato (probablemente ya — el session log dice "Inter+Lato"). Validar en próxima sesión.
- [ ] Cooldown 4: revisar si vale la pena comprar Proxima Nova.
