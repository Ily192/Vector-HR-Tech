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
| Tope de gasto por run | Desactivado por defecto durante la fase de medición (`ENFORCE_RUN_COST_CAP=false`) | `app/domain/presupuesto.py` |

No existe `app/providers/`: la abstracción multi-proveedor vive en
`app/clients/` (un módulo por función: `scoring.py`, `embeddings.py`).

## Actualización 2026-10-19 · razonamiento y ciclo de vida de 2.5

- **El razonamiento se cobraba sin registrarse.** 2.5 Flash razona por defecto,
  y esos tokens se cobran como salida. El costo de cada evaluación solo sumaba
  `candidates_token_count`, así que la fase de medición quedaba por debajo de lo
  real.
  - Ahora suma también `thoughts_token_count`.
  - El razonamiento se apaga con `SCORING_THINKING_BUDGET=0`, que es el valor por
    defecto. Con él encendido, el modelo podía gastar los 1024 tokens de
    `max_output_tokens` razonando y devolver el JSON cortado, y se cobraba igual.
  - Para volver a encenderlo, sube el budget y corre antes los evals del SKILL.md.
  - Fuente: [Thinking](https://ai.google.dev/gemini-api/docs/thinking), "Set
    budget" y "Pricing".
- **Acceso a 2.5.** Desde el 18-09-2026, Google limita los modelos 2.5 a quien ya
  los usaba. Para proyectos nuevos recomienda `gemini-3.5-flash-lite` (al mismo
  precio que 2.5 Flash, 0.30 / 2.50) o `gemini-3.8-flash`.
  - 2.5 no tiene fecha de apagado.
  - Antes del primer deploy, hay que probar la key del proyecto de producción con
    `gemini-2.5-flash`. Si no tiene acceso, se migra a 3.5 Flash-Lite pasando por
    los evals.
  - Gemini 3 usa `thinking_level`, no el budget. Además, el changelog del
    21-07-2026 marca `temperature` y `top_p` como deprecados, y el scoring los usa.
  - Fuentes: [Deprecations](https://ai.google.dev/gemini-api/docs/deprecations),
    [changelog](https://ai.google.dev/gemini-api/docs/changelog) y
    [pricing](https://ai.google.dev/gemini-api/docs/pricing), revisados el
    2026-10-19.

## Actualización 2026-11-13 · el scoring pasa a `gemini-3.5-flash-lite`

- **Por qué ahora.** `gemini-2.5-flash` está deprecado:
  - ya no se puede elegir en AI Studio y responde 404 a claves nuevas (pasó con la de
    producción candidata);
  - desde el 2026-12-01, la API redirige las llamadas a `gemini-3.5-flash-lite` y las
    cobra a su precio.
  - Fuente: [Deprecations](https://ai.google.dev/gemini-api/docs/deprecations) y
    [Models](https://ai.google.dev/gemini-api/docs/models).
- **Qué cambió en el código** (PR 3), según la
  [guía de migración](https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.6):
  - `DEFAULT_SCORING_MODEL=gemini-3.5-flash-lite`, al mismo precio (0.30 / 2.50 USD
    por 1M).
  - `thinking_level` minimal (`SCORING_THINKING_LEVEL`), en lugar del budget.
  - Sin `temperature` ni `top_p`, que en Gemini 3 están deprecados.
  - "minimal" sube a "low" en los modelos que no lo aceptan (3.8 Flash y Gemini 4).
- **Eval del evaluador** (`app/cli/evals_cv_evaluator.py`, set sintético de 8 casos, 3
  repeticiones y 24 pares contrafactuales, el 2026-11-13). No hay línea base de 2.5:
  la clave disponible ya no tiene acceso.

  | Modelo y razonamiento | Pearson r | Acierto (±1,5) | Pares movidos | Resultado | Costo de la corrida |
  |---|---|---|---|---|---|
  | `gemini-3.5-flash-lite` minimal | 0,99 | 100 % | 4 de 24 (Δ 1,0; edad y origen) | NO PASA | US$0,17 |
  | `gemini-3.5-flash-lite` low | 0,99 | 100 % | 8 de 24 (sobre todo edad) | NO PASA | US$0,17 |
  | `gemini-3.8-flash` low | 0,97 | 75 % | 0 de 24 | PASA | US$0,35 |

- **Decisión pendiente (Ilyra) antes de activar la evaluación con IA del plan de pago.**
  El sesgo es condición de ADR-021 §9.
  - El default queda en `gemini-3.5-flash-lite`, el reemplazo oficial, porque el plan
    de pago todavía no está en producción. Con él la prueba de sesgo no pasa.
  - Opciones:
    - (a) `DEFAULT_SCORING_MODEL=gemini-3.8-flash` con `SCORING_THINKING_LEVEL=low`.
      Pasa el sesgo, pero cuesta ~2× y su precio sube a 1.50 / 7.50 desde el
      2027-01-01.
    - (b) Trabajar el SKILL.md de cv-evaluator (la regla de edad) y volver a medir con
      3.5 Flash-Lite.
  - El set sintético es chico: hay que confirmar con el set real antes de producción.

## Alternatives considered

- **Solo OpenAI:** más caro, lock-in.
- **Solo Gemini:** Anthropic y OpenAI tienen ventajas específicas.
- **LiteLLM / OpenRouter:** abstracción extra que aún no justifica costo.
