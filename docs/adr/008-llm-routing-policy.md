# ADR-008: Routing de LLMs — Gemini Flash default, gpt-4o reasoning, Claude code

- **Status:** Accepted
- **Date:** 2026-05-08
- **Tags:** ai, cost, providers

## Context

Necesitamos balancear costo, calidad y latencia entre múltiples LLMs.

## Decision

| Caso de uso | Modelo | Razón |
|---|---|---|
| Embeddings (CV, JD, ICP) | OpenAI `text-embedding-3-small` | Mejor costo/calidad, 1536 dims |
| Scoring rápido (CV fit, lead fit) | **Gemini 1.5 Flash** | $0.075/1M tokens — ~10x más barato que gpt-4o-mini |
| Razonamiento complejo (entrevista, psicométrico, planning) | **OpenAI gpt-4o** | Calidad superior cuando importa |
| Conversación canal (chat HRBP) | gpt-4o-mini o Gemini Flash | Latencia + costo |
| Tool calling estricto / function calling | gpt-4o | Mejor adherencia a JSON schemas |
| Code agents internos (Cursor, Claude Code) | **Claude Sonnet/Opus** | Vibe coding |

Multi-provider obligatorio para evitar lock-in. Abstracción en `app/providers/`.

## Consequences

**Positivas:** costo controlado, fallback entre proveedores, libertad de switchear si suben precios.
**Negativas:** mantener prompts compatibles entre modelos requiere abstraerlos en SKILL.md.

## Reglas operacionales

- **Cost cap por run** desde Paperclip — denegar si excede.
- **Schemas estrictos** (`response_format: json_schema`) cuando aplique.
- **Retries con backoff** en proveedor de fallback si primario falla.
- **PII redactada** antes de logs.

## Alternatives considered

- **Solo OpenAI:** más caro, lock-in.
- **Solo Gemini:** Anthropic y OpenAI tienen ventajas específicas.
- **LiteLLM / OpenRouter:** abstracción extra que aún no justifica costo.
