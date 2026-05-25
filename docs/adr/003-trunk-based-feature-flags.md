# ADR-003: Trunk-based development con feature flags

- **Status:** Accepted
- **Date:** 2026-05-08
- **Tags:** process, devex, releases

## Context

Necesitamos un modelo de branching que:
- Permita deploys diarios con 1 dev FT.
- No acumule deuda en branches "que nunca se mergean".
- Soporte release gradual y kill switches.
- Sea compatible con vibe coding (PR small, merge fast).

## Decision

Adoptar **trunk-based development**: `main` siempre desplegable; branches efímeros (< 2 días); features incompletas detrás de **feature flags**.

- Branches: `feat/<scope>-<short>`, `fix/<scope>-<short>`, `chore/<scope>-<short>`.
- Squash & merge.
- Feature flags vía Unleash self-host (free) o PostHog flags.
- Cada flag tiene fecha de eliminación documentada.

## Consequences

**Positivas:** lead time corto, integración continua real, refactor seguro detrás de flags.
**Negativas:** disciplina extra para gestionar flags (pero auditoría mensual lo controla).

## Alternatives considered

- **GitFlow:** demasiada ceremonia para 1 dev.
- **GitHub Flow puro sin flags:** no permite release gradual ni kill switch.
