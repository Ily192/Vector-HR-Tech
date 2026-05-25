# ADR-006: SKILL.md (formato gstack/openclaw) como unidad de agente

- **Status:** Accepted
- **Date:** 2026-05-08
- **Tags:** agents, skills, evals

## Context

Necesitamos una forma versionable, testeable y vibe-codeable de definir agentes. Los repos `openclaw-main` y `gstack-main` ya proponen un formato consistente.

## Decision

Cada agente vive en `.agents/skills/<name>/`:

```
.agents/skills/<name>/
├── SKILL.md             ← prompt + reglas + ejemplos + cost cap
├── SKILL.md.tmpl        ← template con {{vars}} para multi-tenant
├── agents/
│   └── openai.yaml      ← display_name, short_description, default_prompt
├── evals/
│   ├── golden_set.jsonl
│   ├── regression_set.jsonl
│   └── adversarial.jsonl
└── README.md
```

Versionado semver dentro del propio `SKILL.md`. CI corre evals automáticamente cuando un PR toca `.agents/skills/**`.

## Consequences

**Positivas:** prompts en git con diff legible; evals como tests; copiar-pegar para nuevo skill es trivial; compatible con OpenClaw upstream.
**Negativas:** disciplina de mantener evals actualizadas (mitigado con CI gate).

## Alternatives considered

- **Prompts en Postgres:** difícil PR review, sin evals atadas.
- **LangChain / LlamaIndex prompt registry:** lock-in y abstracciones que no necesitamos.
- **JSON config:** menos legible para prompts largos.
