# candidate

> **Cycle 1 · Semana 2 (entregable 2.2).**
> Vite + React 18 SPA — portal del candidato (dashboard + status + test psicométrico embebido).

Scaffold pendiente. Stack alineado a `apps/hrbp/`:

- Vite 5 + React 18 + TypeScript estricto
- Tailwind con `@vortex/design-tokens` preset
- `@vortex/ui` para componentes
- TanStack Query + Zustand
- Supabase Auth (rol `cliente`/candidato sin sesión persistente — usa magic link)

Rutas planeadas (ver `docs/specs/cycle-01-wireframes.md`):

| Ruta | Descripción |
|---|---|
| `/` | Dashboard del candidato (estado de aplicaciones) |
| `/applications/:id` | Detalle de una aplicación + timeline |
| `/test/:token` | Test psicométrico (iframe vs componente nativo — ver ADR-014) |
| `/profile` | Datos personales editables |

Deploy en Vercel — proyecto separado, mismo monorepo (`apps/candidate`).
