# orgchart

> **Cycle 2 — Org Chart Vortex (mirror Paperclip).**
> Next.js 14 — visualización del organigrama vivo del tenant.

Scaffold pendiente. Bloqueado por:

1. Paperclip self-host estable (Cycle 1 tarea 1.1).
2. Endpoint `GET /orgchart/:empresa_id` exponiendo el árbol jerárquico.

Stack planeado:

- Next.js 14 App Router + TypeScript estricto
- `@vortex/ui` + `@vortex/design-tokens`
- `react-flow` para el árbol interactivo (zoom + drag + expand/collapse)
- Server Components + suspense streaming desde Paperclip

Deploy en Vercel — proyecto separado.
