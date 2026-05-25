<!--
PR Title: usa Conventional Commits
  feat(scope): short description
  fix(scope): short description
  chore(scope): short description
-->

## Contexto

<!-- Por qué este PR existe. Issue / pitch enlazado. -->

Closes #

## Cambios

<!-- Qué cambió, en bullets. -->

-
-

## Tipo de cambio

- [ ] feat — nueva funcionalidad
- [ ] fix — bug
- [ ] chore — refactor / build / deps
- [ ] docs — documentación
- [ ] test — solo tests

## Vibe coding

<!-- Transparencia obligatoria. -->

- Hecho por humano:
- Hecho por agente (Claude/Cursor):

## Definition of Done

- [ ] Lint + typecheck verde
- [ ] Tests unit + integration verdes
- [ ] Coverage no baja respecto a `main`
- [ ] Conventional Commit en title
- [ ] Sin secretos / sin `console.log` / sin `TODO` huérfano

### Si toca DB

- [ ] Migration generada + revisada a mano
- [ ] Down-migration escrita
- [ ] RLS policy + test si tabla nueva tiene `empresa_id`

### Si toca SKILL

- [ ] `SKILL.md` versionado (semver)
- [ ] Eval suite pasa umbral
- [ ] Costo estimado documentado

### Si toca UI

- [ ] Storybook story por estado
- [ ] axe-core sin violations
- [ ] Screenshot mobile + desktop, light + dark
- [ ] Keyboard nav verificado

### Si toca seguridad / auth

- [ ] Threat model actualizado
- [ ] RBAC/ABAC tests pasan
- [ ] Aprobación adicional Ilyra

## Riesgos

<!-- Qué puede salir mal. Cómo lo mitigamos. -->

## Screenshots / video

<!-- Para UI o features visibles. -->

## Notas para reviewer

<!-- Algo específico que mirar. -->
