# 02 · Methodology — Cómo trabajamos

## 1. Modelo elegido: Shape Up adaptado + Trunk-based development

| Pieza | Origen | Por qué |
|---|---|---|
| **Ciclos de 2 semanas + 1 semana cooldown** | Shape Up (Basecamp), reducido | Equipo de 1, no necesitamos 6 semanas |
| **Pitches (no backlog)** | Shape Up | Evita acumulación de tickets viejos; cada cycle se "apuesta" |
| **Trunk-based development** | Stripe / Google / GitHub | `main` siempre desplegable, sin gitflow ceremonioso |
| **Feature flags** | LaunchDarkly / Unleash / OSS | Ship continuo sin esperar QA manual |
| **DORA metrics** | Google DORA report | Medimos delivery, no horas |
| **Evals como tests para agentes** | Anthropic / OpenAI / gstack | Los SKILL.md tienen su propia suite |

### Por qué NO Scrum / SAFe

- **Scrum:** ceremonias para 5+ personas; daily standup, sprint review, retro suman 8h/semana — desperdicio para 1 dev.
- **SAFe:** diseñado para 50-150 personas distribuidas en trenes de release. Overkill absoluto.
- **Kanban puro:** no marca cadencia, riesgo de drift indefinido.
- **Waterfall:** veta cualquier aprendizaje del cliente piloto.

### Por qué Shape Up encaja

- **Appetite, no estimación:** decidimos cuánto valor merece una idea, no cuánto tarda.
- **Hill Charts** en vez de % de progreso (refleja descubrimiento, no ejecución lineal).
- **Cooldown de 1 semana** entre cycles para refactor + tech debt + research del próximo pitch.

## 2. Cadencia

```
Semana 1-2 : Cycle 1 (build)        ──┐
Semana 3   : Cooldown (refactor)    ──┤  Iteración Q1 (4 semanas)
Semana 4-5 : Cycle 2 (build)        ──┘
...
```

**MVP = Cycles 1-2** (4 semanas). Después, ritmo sostenido cycle/cooldown.

### Ceremonias mínimas

| Cuándo | Qué | Duración | Output |
|---|---|---|---|
| Lunes cycle | Pitch & bet | 30 min solo | Pitch escrito en `docs/specs/cycle-NN.md` |
| Lunes cycle | Kickoff | 15 min | Hill chart inicial |
| Diario | Self-standup escrito | 5 min | Update en `docs/runbooks/daily.md` (rolling) |
| Viernes semana 1 | Mid-cycle review | 30 min | Hill chart actualizado, decidir scope-cuts |
| Viernes cycle | Cycle review + retro | 1h | Lo que envió, lo que quedó, qué aprendimos |
| Viernes cooldown | Pitch del próximo cycle | 1h | Documento listo para apuesta |

> Como el equipo es de 1, "ceremonias" = escribir las decisiones para tu yo futuro y para el cliente.

## 3. Ciclo de desarrollo (SDLC)

Modelo híbrido: **iterativo-incremental con descubrimiento continuo**.

```
            Discover
               │
               ▼
   Shape (pitch) ──► Bet (cycle plan)
                        │
                        ▼
              Build ◄──► Test (TDD donde aplica)
                        │
                        ▼
                    Validate
              (evals + e2e + cliente piloto)
                        │
                        ▼
                    Ship (CD)
                        │
                        ▼
                    Operate
              (observability + on-call)
                        │
                        ▼
                  Learn ──► (back to Discover)
```

**Sin fases tipo waterfall**. Cada PR atraviesa el ciclo en horas.

## 4. Branching y commits

- **Trunk-based.** `main` siempre verde y deployable.
- **Branches efímeros** (< 2 días):
  - `feat/<scope>-<short>` — nueva feature.
  - `fix/<scope>-<short>` — bug.
  - `chore/<scope>-<short>` — refactor, build, deps.
  - `docs/<scope>-<short>` — solo docs.
- **Conventional Commits** para commits y PR titles:
  - `feat(hr-engine): add sourcer worker with vector match`
  - `fix(control-plane): respect budget hard-stop on overage`
  - `chore(ci): bump pnpm to 9.7`
- **Squash & merge** por defecto (historia limpia en main).
- **PR template** obligatorio: contexto, cambio, tests, screenshots si UI.

## 5. Definition of Ready (DoR) y Definition of Done (DoD)

### DoR — antes de empezar a codear un pitch

- [ ] Pitch escrito (problem, appetite, solution sketch, no-gos).
- [ ] Hill chart inicial creado.
- [ ] ADR escrita si la decisión arquitectónica es nueva.
- [ ] Acceptance criteria explícitos.

### DoD — antes de mergear

- [ ] Tipa: tests unit + integration pasan.
- [ ] Lint + typecheck verde.
- [ ] Coverage no baja respecto a `main`.
- [ ] Si toca skill: eval suite pasa con score umbral.
- [ ] Si toca UI: screenshot Storybook + Playwright trace.
- [ ] Si toca migration: revisada por humano + dry-run en staging.
- [ ] PR template completo.
- [ ] Reviewer (humano o Claude code-review agent) aprueba.

Detalle en [11_QUALITY_GATES.md](11_QUALITY_GATES.md).

## 6. Métricas de delivery (DORA)

Tracked en `docs/runbooks/dora.md` con script semanal.

| Métrica | Target MVP | Target maduro |
|---|---|---|
| Lead time (commit → prod) | < 1 día | < 1 hora |
| Deploy frequency | diario | múltiples por día |
| Change failure rate | < 20% | < 15% |
| MTTR | < 4 h | < 1 h |

## 7. Vibe coding como práctica formal

- **Pair con Claude/Cursor** es el modo default. No es "plus", es la forma de trabajar.
- **Cada PR debe explicar qué hizo el humano vs el agente** en la descripción (transparencia).
- **Skills de Claude** (autoplan, benchmark, code-review) viven en `.agents/skills/` del repo y son versionadas.
- **Eval gate:** antes de mergear cambios a `services/hr-engine`, corre eval suite contra fixtures reales.

## 8. Documentación viva

- **ADRs** en `docs/adr/NNN-titulo-corto.md` (formato Michael Nygard).
- **Runbooks** en `docs/runbooks/` — uno por flujo crítico (deploy, rollback, on-call, incidente).
- **Specs** en `docs/specs/cycle-NN.md` — pitch + acceptance criteria.
- **Onboarding** en `docs/onboarding/` — cómo arrancar de cero.

> Regla: si no está documentado, no existe. Si está en Slack/WhatsApp, no existe en 2 semanas.

## 9. Comunicación con cliente piloto

- **Loom semanal** (2-3 min) con avances visibles.
- **Changelog público** auto-generado desde Conventional Commits.
- **Status page** simple (`/status`) con uptime + degradaciones recientes.

---

*Siguiente: [03 · Architecture](03_ARCHITECTURE.md)*
