---
name: sourcer
version: 0.1.1
description: Encuentra y rankea candidatos según el ICP del HRBP. Devuelve top-N con score 0-10, rationale y gaps.
owner: Vortex Ops · HR engine
domain: hr
inputs:
  - vacante_id (uuid, opcional si viene icp_text)
  - icp_text (string, opcional si viene vacante_id)
  - target (int, default 50)
  - sources (internal | linkedin | bumeran)
outputs:
  - candidate_id
  - full_name
  - headline
  - score (0-10)
  - rationale
  - gaps (lista)
  - source
models:
  # Tiene que coincidir con DEFAULT_SCORING_MODEL del hr-engine. Sin fallback:
  # el código no tiene ninguno. Lo vigila services/hr-engine/tests/unit/test_skills.py.
  default: gemini-2.5-flash
# Sin tope: fase de medición de costes (2026-10). Ver ENFORCE_RUN_COST_CAP
# y services/hr-engine/scripts/informe_costes.py.
cost_cap_usd: null
tags:
  - hr
  - sourcing
  - cycle-1
---

# Sourcer-Bot

> Encuentra y rankea candidatos según el ICP del HRBP.

- **Channel:** invocado desde `hr-engine/workers/sourcer.py` o conversacionalmente desde OpenClaw
- **Cost cap:** override por tenant en Paperclip (el valor base vive en `cost_cap_usd` del frontmatter)

## Purpose

Dado un `vacante_id` (o ICP libre en texto), buscar candidatos relevantes en:
1. Base interna (`candidatos` en Supabase con embeddings vectoriales).
2. Fuentes públicas (LinkedIn pública, GitHub jobs, Bumeran, Computrabajo) — solo si el tenant lo habilita.

Devolver top-N candidatos con score, brechas detectadas y razón breve.

## Inputs

```yaml
vacante_id: uuid           # opcional si se pasa icp_text
icp_text: string           # opcional si se pasa vacante_id
target: int = 50           # cantidad de candidatos a retornar
sources: ["internal", "linkedin", "bumeran"]  # default: ["internal"]
```

## Output schema (Pydantic strict)

```python
class CandidateScored(BaseModel):
    candidate_id: UUID | None       # None si es source externa nueva
    full_name: str
    headline: str
    score: float                    # 0-10
    rationale: str                  # 1-2 frases
    gaps: list[str]                 # brechas vs ICP
    source: Literal["internal", "linkedin", "bumeran", "github"]
    raw_url: HttpUrl | None
```

## Rules / Guardrails

1. **No alucinar candidatos.** Si la fuente no devolvió nada, retornar lista vacía con razón.
2. **Respetar blacklist de la empresa** (`empresas.blacklist_dominios`).
3. **No PII en logs:** redactar email/teléfono.
4. **Rate limit por fuente:**
   - LinkedIn pública: 1 req/2s, max 100/run.
   - Bumeran: 1 req/1s, max 200/run.
5. **Idempotencia:** mismo input + mismo timestamp de día → mismo output (cache 24h).
6. **Compliance:** datos de fuentes públicas solo se persisten si el tenant tiene base legal (consentimiento o interés legítimo declarado).
7. **Puntuación de cada candidato:** usa las reglas del SKILL.md de `cv-evaluator` —calibración del score y regla anti-sesgo—, que es exactamente lo que recibe el modelo. No se repiten aquí para que no puedan divergir.

## Few-shot examples

(Ver `evals/golden_set.jsonl` para casos completos.)

### Ejemplo 1

**Input:**
```yaml
vacante_id: 11111111-...
icp_text: "Senior Software Engineer, 5+ años Python, experiencia microservicios y AWS, español-inglés"
target: 5
sources: ["internal"]
```

**Output esperado:** lista de 5 candidatos con `score >= 7` y rationale específico.

## Eval criteria

| Metric | Threshold |
|---|---|
| Recall@10 vs ground truth humano | ≥ 0.7 |
| Precisión score (Pearson r) | ≥ 0.75 |
| Rationale coherence (LLM-as-judge) | ≥ 4/5 |
| Output schema válido | 100% |

## Cost expectations

- Input tokens promedio: ~2,500 (vacante + ICP + 50 perfiles top-K).
- Output tokens promedio: ~800 (50 candidatos × 16 tokens).
- Costo: ~$0.0007/run, estimado con Gemini 1.5 Flash, ya retirado. Pendiente de re-medir con 2.5 Flash.
- Costo embedding inicial: ~$0.0001 si vacante no embeddida.

## Changelog

- **0.1.1 (2026-10-05):** modelo `gemini-1.5-flash` (retirado) → `gemini-2.5-flash`, fuera el
  fallback que el código no tiene, y la regla 7: la puntuación usa las reglas de `cv-evaluator`.
- **0.1.0 (2026-05-08):** initial skill, internal source only.
