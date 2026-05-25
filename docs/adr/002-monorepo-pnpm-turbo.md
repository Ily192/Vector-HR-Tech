# ADR-002: Monorepo pnpm + Turborepo para frontends; servicios Python independientes

- **Status:** Accepted
- **Date:** 2026-05-08
- **Tags:** repo, devex

## Context

Tenemos 4 frontends (`career-site`, `candidate`, `hrbp`, `orgchart`) que comparten:
- Tokens de diseño (Vector HR brand)
- Componentes UI base (shadcn/ui customizado)
- Cliente Supabase tipado
- Tipos compartidos (Zod schemas)
- Auth helpers

Y 4 backends (`control-plane` Node, `agent-plane` TS, `hr-engine` Python, `sales-engine` Python).

## Decision

- **Monorepo único** en raíz `Vortex-Ops/`.
- **pnpm workspaces** + **Turborepo** para todo lo TS/JS (`apps/*`, `packages/*`).
- **Servicios Python** son sub-proyectos independientes con su propio `pyproject.toml` (uv), **fuera** del workspace pnpm pero dentro del repo.
- Turbo orquesta tasks JS; Python tasks invocados via scripts de shell o Make.

## Consequences

**Positivas:**
- Cambio en `packages/design-tokens` se propaga atómicamente a todos los frontends.
- Caché remoto de Turbo acelera CI 3-10x.
- Code review con visión completa del cambio cross-stack.

**Negativas:**
- CI un poco más complejo (matrix por servicio).
- Tamaño del repo crece — mitigado con sparse checkout para devs específicos.

## Alternatives considered

- **Polyrepo:** descartado — fricción de cambios cross-paquete.
- **Nx:** más features pero curva mayor; Turbo cubre lo que necesitamos.
- **Lerna:** legacy, deprecado.
