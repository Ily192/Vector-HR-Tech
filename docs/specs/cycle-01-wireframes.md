# Cycle 1 · Wireframes (markdown)

> No usamos Figma para v0 (justifico: 1 dev FT, mejor invertir las horas en código). Estos wireframes en markdown son **suficientes para implementar** porque ya tenemos `@vortex/ui` + `@vortex/design-tokens` y referencias visuales en `apps/career-site/src/app/page.tsx` y `apps/hrbp/src/App.tsx`.
>
> Cuando haya recursos para diseño dedicado (post-Cycle 4), migrar a Figma con design tokens conectados via Tokens Studio.

---

## career-site

### Rutas

| Ruta | Implementación |
|---|---|
| `/` | ✅ ya implementado (`apps/career-site/src/app/page.tsx`) |
| `/vacantes` | ✅ ya implementado (lista) |
| `/vacantes/[slug]` | ✅ ya implementado (detalle) |
| `/vacantes/[slug]/aplicar` | ⏳ Cycle 1 wk2 — entregable 2.1 |
| `/contacto` | ⏳ futuro (link en hero ya existe) |

### `/vacantes/[slug]/aplicar` — Form de aplicación

Layout (mobile-first, container `max-w-2xl`):

```
┌──────────────────────────────────────────┐
│ Wordmark Vortex                          │
├──────────────────────────────────────────┤
│ ← Volver a la vacante                    │
│                                          │
│ # Aplicar a {vacante.title}              │
│ {vacante.modality} · {vacante.location}  │
│                                          │
│ ┌─ Card ─────────────────────────────┐  │
│ │ Datos personales                   │  │
│ │  [Nombre completo*]                │  │
│ │  [Email*]                          │  │
│ │  [Teléfono]                        │  │
│ │  [LinkedIn URL]                    │  │
│ │                                    │  │
│ │ Tu CV                              │  │
│ │  [📎 Subir PDF (máx 5 MB)*]        │  │
│ │  ↑ drag-and-drop también           │  │
│ │                                    │  │
│ │ ¿Por qué te interesa? (opcional)   │  │
│ │  [textarea 4 líneas]               │  │
│ │                                    │  │
│ │ ☐ Acepto el tratamiento de datos   │  │
│ │   (LGPD link)                      │  │
│ │                                    │  │
│ │ [Enviar aplicación →] (CTA orange) │  │
│ └────────────────────────────────────┘  │
│                                          │
│ Footer minimal (©, link a vector-hr)     │
└──────────────────────────────────────────┘
```

**Comportamiento:**

1. Validación client-side con Zod (`@vortex/types::ApplicationCreateSchema` — agregar).
2. Upload del CV a Supabase Storage bucket `cvs/` con path `{empresa_id}/{candidato_id}/{file.ext}`. RLS: anon puede insert solo en su propio path.
3. Post: crear `candidatos` + `applications` row (status='applied'). Server Action de Next 14.
4. Tras submit → redirect a `/aplicar/success?token={magic_link}` con magic link al portal candidato.
5. Trigger Celery task `cv_evaluator.run` async para scoring.
6. Email transaccional vía Supabase Auth magic link.

**A11y:**

- Labels asociados a inputs con `htmlFor`.
- `aria-required` en campos obligatorios.
- Mensaje de error con `role="alert"`.

**States:**

- `idle` → `submitting` (loader en botón) → `success` (redirect) / `error` (toast).

---

## candidate (Vite SPA — `apps/candidate/`)

### Rutas

| Ruta | Descripción |
|---|---|
| `/` | Dashboard (lista aplicaciones del candidato logueado) |
| `/applications/:id` | Detalle de aplicación + timeline |
| `/test/:token` | Test psicométrico iframe (ADR-014) |
| `/profile` | Datos personales editables |

### `/` Dashboard

```
┌──────────────────────────────────────────┐
│ Wordmark Vortex · avatar candidato · ⌄   │
├──────────────────────────────────────────┤
│ # Hola, {full_name} 👋                   │
│ Estas son tus aplicaciones activas.      │
│                                          │
│ ┌─ Card (por aplicación) ───────────┐   │
│ │ {vacante.title}                   │   │
│ │ {empresa.name} · {modality}       │   │
│ │ Status: [Badge variant según]     │   │
│ │  • applied (gris)                 │   │
│ │  • evaluated (orange) → fit_score │   │
│ │  • interviewed (cian)             │   │
│ │  • hired (success-green)          │   │
│ │  • rejected (danger-red)          │   │
│ │                                   │   │
│ │ Última actualización: hace 2h     │   │
│ │ [Ver detalle →]                   │   │
│ └───────────────────────────────────┘   │
│ ┌─ Card ────────────────────────────┐   │
│ │ ...                               │   │
│ └───────────────────────────────────┘   │
│                                          │
│ Empty state: "Aún no aplicaste a nada.   │
│ [Ver vacantes abiertas →]"               │
└──────────────────────────────────────────┘
```

### `/test/:token`

```
┌──────────────────────────────────────────┐
│ Wordmark · "Test psicométrico"           │
├──────────────────────────────────────────┤
│ [iframe sandboxed con HTML estático]     │
│  - sandbox="allow-scripts                │
│             allow-same-origin"           │
│  - validar event.origin en postMessage   │
│                                          │
│ Iframe envía:                            │
│   { type: 'psicometrico.completed',      │
│     token, results: {...} }              │
│                                          │
│ Al recibir → POST /api/psicometrico/     │
│   submit con token y JSON.               │
│                                          │
│ → redirect a /applications/:id           │
└──────────────────────────────────────────┘
```

---

## hrbp (Vite SPA — `apps/hrbp/`)

### Rutas

| Ruta | Estado |
|---|---|
| `/` | ✅ cockpit con KPIs + pipeline mock (`apps/hrbp/src/App.tsx`) |
| `/vacantes` | ⏳ lista vacantes propias |
| `/vacantes/:id` | ⏳ detalle + kanban candidatos (entregable 2.3) |
| `/vacantes/new` | ⏳ form de creación + auto-generación ICP |
| `/candidatos/:id` | ⏳ detalle candidato (timeline + score history) |
| `/runs` | ⏳ últimos agent runs + status + cost |

### `/vacantes/:id` — Pipeline kanban (entregable 2.3)

```
┌─────────────────────────────────────────────────────────────────┐
│ ← Vacantes  ·  # Senior Software Engineer                       │
│ [open] · 45 candidatos · creada hace 5d   [Editar] [+ Sourcing]│
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐│
│ │Aplicados │ │Evaluados │ │Shortlist │ │Entrevista│ │ Oferta ││
│ │   12     │ │    8     │ │    3     │ │    2     │ │   1    ││
│ ├──────────┤ ├──────────┤ ├──────────┤ ├──────────┤ ├────────┤│
│ │ [Card ↓] │ │ [Card ↓] │ │ [Card ↓] │ │ [Card ↓] │ │[Card↓] ││
│ │ [Card ↓] │ │ [Card ↓] │ │ [Card ↓] │ │ [Card ↓] │ │        ││
│ │  ...     │ │  ...     │ │          │ │          │ │        ││
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘│
└─────────────────────────────────────────────────────────────────┘
```

**Card de candidato (drag-target):**

```
┌─────────────────────────────────────┐
│ {full_name}                         │
│ {headline}                          │
│ ─────────────────────────           │
│ ●●●●●●●●○○  fit_score 8.2/10        │
│ Strengths: python, async, postgres  │
│ Gaps: liderazgo                     │
│                                     │
│ recommended: entrevista 🎯          │
│ aplicó hace 2h                      │
└─────────────────────────────────────┘
```

**Comportamiento:**

1. Datos via Supabase Realtime channel `applications:vacante_id=eq.{id}`.
2. Drag-and-drop entre columnas → mutation `applications.status`.
3. Click en card → drawer lateral con timeline + detalle (no full page).
4. Botón `+ Sourcing` → trigger `sourcer.run` con target=50.

**Stack interno:**

- `@dnd-kit/core` para drag-and-drop accesible.
- `@tanstack/react-query` + Supabase Realtime para sync.
- Optimistic updates.

### `/runs` — Agent runs feed

```
┌─────────────────────────────────────────────────────────┐
│ # Runs de agentes (últimos 50)                          │
│ Filtros: [skill ⌄] [status ⌄] [empresa ⌄] [refresh]    │
├─────────────────────────────────────────────────────────┤
│ ● sourcer.run · completed · 12s · $0.018                │
│   vacante "Senior Python" · 42 candidatos               │
│   hace 3 min                                            │
├─────────────────────────────────────────────────────────┤
│ ● cv_evaluator.run · completed · 4s · $0.002            │
│   candidato "Ana Dev" · score 8.5                       │
│   hace 5 min                                            │
├─────────────────────────────────────────────────────────┤
│ ⚠ cv_evaluator.run · capped · 2s · $0.050               │
│   cost cap excedido                                     │
│   hace 12 min                                           │
└─────────────────────────────────────────────────────────┘
```

---

## Tokens UI usados (referencia rápida)

| Token | Uso |
|---|---|
| `bg-vector-cian-dark-500` | Fondos hero / autoridad |
| `text-vector-cian-electric-500` | Acentos tech / status live |
| `text-vector-orange-500` | CTAs / rebeldía / fit_score color |
| `bg-success-500` / `text-success-500` | hired / completed |
| `bg-warning-500` / `text-warning-500` | needs attention |
| `bg-danger-500` / `text-danger-500` | rejected / failed |
| `shadow-glow-cyan` | Cards de IA con destaque |
| `animate-shimmer-cyan` | Loading skeletons |

---

## Checklist de implementación Cycle 1 wk2

- [ ] 2.1 career-site `/vacantes/[slug]/aplicar` → CV upload + Supabase Storage RLS.
- [ ] 2.2 candidate scaffold (Vite + rutas) + `/` dashboard + `/test/:token`.
- [ ] 2.3 hrbp `/vacantes/:id` con kanban realtime.
- [ ] 2.4 Skill `chro-intake` (no en estos wireframes — es backend).
- [ ] 2.5 cv-evaluator golden set ≥ 10 cases + pearson ≥ 0.75.
- [ ] 2.6 OpenClaw → hr-engine via run-token JWT.
- [ ] 2.7 E2E Playwright: "Subir CV → ver score en hrbp en < 2 min".
- [ ] 2.8 Loom demo público 5 min.
