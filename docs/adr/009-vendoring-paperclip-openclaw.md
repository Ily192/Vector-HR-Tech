# ADR-009: Vendoring (no submodule) de paperclip-master y openclaw-main

- **Status:** Accepted
- **Date:** 2026-05-08
- **Tags:** dependencies, repo-management

## Context

Necesitamos integrar `paperclip-master` (control plane) y `openclaw-main` (agent plane). Tres opciones:

1. Git submodule.
2. Vendoring (copiar el código en `services/control-plane/vendor/`, `services/agent-plane/vendor/`).
3. Fork mantenido como repo aparte y publicado como package.

## Decision

**Vendoring** dentro de `services/control-plane/` y `services/agent-plane/`, con un script `scripts/sync-upstream.sh` que actualiza desde tags upstream. Todos los plugins/extensiones de Vortex viven al lado, no dentro del vendored code.

## Consequences

**Positivas:**
- Cero submodule fragility (`.gitmodules`, init/update, CI flakiness).
- Build determinista — el código que se ejecuta es el código que está en `main`.
- Patches custom posibles sin fork (con marca clara `// VORTEX-PATCH:`).

**Negativas:**
- Updates manuales (no automáticos como Dependabot puede hacer con npm/pip).
- Repo crece en tamaño.

**Mitigaciones:**
- Script `sync-upstream.sh` corrido manualmente cuando upstream tiene tag relevante.
- CI compara hash de vendored code con upstream tag → comment en PR si hay drift.

## Alternatives considered

| Alternativa | Por qué descartada |
|---|---|
| Submódulo Git | Fragilidad histórica, problemas en CI con clones shallow |
| Fork público + dep | Overhead operacional, otro repo para mantener |
| npm/pip packages publicados | Paperclip y OpenClaw no publican packages estables |
