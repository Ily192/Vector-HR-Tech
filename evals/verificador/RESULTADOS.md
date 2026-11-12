# Verificador de vacantes: comparación de modelos

Corrida del 2026-11-12 21:50 UTC con `python -m app.cli.evals_verificador` (services/hr-engine). Set sintético `casos.yaml`: 40 vacantes inventadas de México y Venezuela (22 legítimas, 13 de riesgo alto y 5 de riesgo medio). Mismo prompt para todos (`instrucciones.md`), salida estructurada con el esquema del script y una sola pasada por modelo.

- Claude: `thinking` adaptativo, `effort: low`, `output_config.format`. Opus 5.5 y Sonnet 5.5 con `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`); Haiku 5.5 no tiene fallback del lado del servidor y su negativa cuenta como revisión manual.
- Gemini: `generate_content` con `response_json_schema`; 2.5 con `thinking_budget=0` (como el hr-engine hoy) y los 3.x con `thinking_level=LOW`.
- Los modelos de Claude están listos en el script pero apagados por defecto (`--con-claude`): hoy no hay créditos en la API de Anthropic.

Criterio: el más barato con recall de alto = 100%, ninguna sospechosa como bajo y falsos positivos ≤ 10%.

## Resultados

Todavía no corrió ningún modelo.

Sin correr:
- `claude-haiku-5-5`: apagado: sin créditos en la API de Anthropic (se activa con --con-claude)
- `claude-sonnet-5-5`: apagado: sin créditos en la API de Anthropic (se activa con --con-claude)
- `claude-opus-5-5`: apagado: sin créditos en la API de Anthropic (se activa con --con-claude)
- `gemini-2.5-flash`: falta GOOGLE_API_KEY
- `gemini-3.5-flash-lite`: falta GOOGLE_API_KEY
- `gemini-3.8-flash`: falta GOOGLE_API_KEY

Gasto de la corrida: US$0.0000 (tope US$2.00).

## Recomendación

Ningún modelo corrió el set completo: no hay recomendación todavía.

## Estimación antes de correr

| Modelo | Precio (entrada / salida por millón) | Estimado para el set | Fuente |
|---|---|---|---|
| `claude-haiku-5-5` | US$0.10 / US$0.50 | ~US$0.010 | skill claude-api, tabla Current Models (2026-11-03). |
| `claude-sonnet-5-5` | US$2.00 / US$10.00 | ~US$0.207 | skill claude-api, tabla Current Models (2026-11-03). |
| `claude-opus-5-5` | US$4.00 / US$20.00 | ~US$0.414 | skill claude-api, tabla Current Models (2026-11-03). |
| `gemini-2.5-flash` | US$0.30 / US$2.50 | ~US$0.043 | https://ai.google.dev/gemini-api/docs/pricing. el del hr-engine hoy; deprecado, desde el 2026-12-01 se redirige a 3.5 Flash-Lite. |
| `gemini-3.5-flash-lite` | US$0.30 / US$2.50 | ~US$0.043 | https://ai.google.dev/gemini-api/docs/pricing. el Flash-Lite vigente y el reemplazo oficial de 2.5 Flash. |
| `gemini-3.8-flash` | US$0.75 / US$3.75 | ~US$0.078 | https://ai.google.dev/gemini-api/docs/pricing. el Flash más nuevo; sube a US$1,50 / US$7,50 desde el 2027-01-01. |
| `gemini-2.5-flash-lite` | US$0.10 / US$0.40 | ~US$0.009 | https://ai.google.dev/gemini-api/docs/pricing. no deprecado, pero la API solo lo da a quien ya lo usaba; solo con --modelos. |
