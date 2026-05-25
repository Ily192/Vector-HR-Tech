# ADR-014 · Test psicométrico: iframe del HTML estático (v0)

- **Status:** Accepted
- **Fecha:** 2026-05-25
- **Decisores:** Ilyra
- **Relacionado:** Portafolio `Test-psicometricos/` (HTML estático existente)

## Contexto

El test psicométrico es uno de los pasos del HR pipeline. Existe ya como HTML estático en `Test-psicometricos/` del Portafolio. Opciones:

1. **Embeber como iframe** — el HTML legacy se sirve desde Supabase Storage o desde `apps/candidate/public/test/index.html`, el portal le pasa el token vía query string.
2. **Reescribir como React component nativo** — pull questions desde Supabase, render con `@vortex/ui`, persistir respuestas con RLS.

Opción 1 es ~1h. Opción 2 es ~10-15h (mantener escala + scoring + branching logic + persistencia + tests).

## Decisión

**v0 (Cycle 1): iframe del HTML estático.**

- `apps/candidate/public/psicometrico/` aloja el HTML legacy intacto.
- Ruta `/test/:token` en `apps/candidate` valida token contra tabla `psicometricos`, monta iframe con `?token=...`.
- Iframe `postMessage` al portal cuando el candidato envía resultados — el portal hace POST a `hr-engine/api/psicometrico/submit`.
- `sandbox="allow-scripts allow-same-origin"` en el iframe para aislamiento.

**Reescritura nativa:** Cycle 3 si métricas justifican (drop-off rate del test alto, accesibilidad limitada en iframe).

## Consecuencias

### Positivas

- 1h vs 15h. Permite cerrar Cycle 1 DoD ("Subir CV → ver score") en plazo.
- HTML legacy ya está probado en producción (Portafolio `Portal-HR-TH`).
- `postMessage` con origen estricto es seguro si validamos `event.origin`.

### Negativas

- Accesibilidad menor (WCAG 2.2 AA es harder de auditar en iframe ajeno).
- Tema dark/light no comparte tokens con el resto del portal. Aceptamos visual disonance para v0.
- Móvil: iframes pueden tener bugs de scroll en Safari iOS. Documentar workaround si aparece.

## Acciones

- [x] ADR documentada.
- [ ] Cycle 1 wk2: copiar HTML estático a `apps/candidate/public/psicometrico/`.
- [ ] Implementar handler `postMessage` con validación de origin.
- [ ] Cycle 3: medir drop-off del test — si > 30%, reescribir nativo.
