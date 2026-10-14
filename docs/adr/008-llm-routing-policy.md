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

## Actualización 2026-10-14 · lo que ejecuta hoy el código

La tabla de arriba es la decisión original (mayo 2026). Donde el código ya se
apartó de ella, manda esto:

| Caso | Hoy en el código | Dónde |
|---|---|---|
| Scoring (cv-evaluator y sourcer) | `gemini-2.5-flash`, a 0.30 / 2.50 USD por 1M tokens (entrada / salida). `gemini-1.5-flash` está retirado | `app/config.py::default_scoring_model`, `app/clients/scoring.py::_PRICING_USD_PER_1M` |
| Respaldo de scoring | `gpt-5-mini` vía OpenAI Responses API, con el mismo SKILL.md y esquema. No hay fallback a `gpt-4o-mini` | `fallback_scoring_model`, `_score_con_openai` |
| Disponibilidad | Circuit breaker por proveedor en Redis; si caen todos, la evaluación se aplaza y luego pasa a revisión manual | `app/clients/circuit_breaker.py`, `app/workers/run_state.py` |
| Siguiente paso del candidato | Lo decide una regla fija según el score, no el modelo | `app/domain/siguiente_paso.py` |
| Tope de gasto por run | Desactivado por defecto durante la fase de medición (`ENFORCE_RUN_COST_CAP=false`) | `app/workers/cost_tracker.py` |

No existe `app/providers/`: la abstracción multi-proveedor vive en
`app/clients/` (un módulo por función: `scoring.py`, `embeddings.py`).

## Alternatives considered

- **Solo OpenAI:** más caro, lock-in.
- **Solo Gemini:** Anthropic y OpenAI tienen ventajas específicas.
- **LiteLLM / OpenRouter:** abstracción extra que aún no justifica costo.
