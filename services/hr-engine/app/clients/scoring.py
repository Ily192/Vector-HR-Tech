"""Scoring candidato↔ICP con Gemini — structured output JSON.

Migración (2026-09): `google.generativeai` está deprecado (el propio SDK emite
aviso de fin de soporte) y `gemini-1.5-flash` es una generación retirada. Este
módulo usa el SDK vigente **`google-genai`** (`from google import genai`) y
`gemini-2.5-flash` como default.

Resiliencia:
- Timeout explícito por request (`GEMINI_TIMEOUT_SECONDS`; el SDK lo toma en ms).
- Retries sobre las excepciones reales (`google.genai.errors.ServerError`,
  `ClientError` 429, timeouts httpx) vía `app.clients.errors`.

Privacidad: los logs de este módulo NO llevan PII. El prompt contiene el CV de
una persona real, así que nunca logueamos `response.text` crudo ni el nombre
del candidato; usamos un hash corto (`candidate_ref`) que permite correlacionar
sin exponer identidad.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.clients.errors import is_retryable_llm_error, log_retry_attempt
from app.config import settings
from app.monitoring import hash_pii, logger

#: Pricing USD por 1M tokens. Fuente: Google AI pricing (2026-09).
_PRICING_USD_PER_1M: dict[str, tuple[float, float]] = {
    # modelo: (input, output)
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-pro": (1.25, 10.00),
}
_DEFAULT_PRICING = (0.30, 2.50)


class CandidateFitResponse(BaseModel):
    """Schema estricto del output que Gemini debe devolver."""

    score: float = Field(ge=0, le=10)
    rationale: str = Field(min_length=10)
    gaps: list[str]
    strengths: list[str]
    recommended_next_step: Literal["psicometrico", "entrevista", "rechazar"]


@dataclass(slots=True, frozen=True)
class ScoringResult:
    response: CandidateFitResponse
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str


_SYSTEM_INSTRUCTION = (
    "Sos un evaluador HR senior. Evalúa el fit candidato↔vacante con "
    "rigor. Salida ESTRICTA en JSON matching el schema. No inventes "
    "experiencia que no está en el CV. Sé conciso (rationale ≤ 300 "
    "palabras). Idioma: español neutro LATAM."
)


@lru_cache(maxsize=1)
def _get_client() -> genai.Client:
    if not settings.google_api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY no configurada — scoring Gemini desactivado. Setear en .env o Doppler.",
        )
    return genai.Client(
        api_key=settings.google_api_key,
        # `HttpOptions.timeout` va en MILISEGUNDOS.
        http_options=types.HttpOptions(
            timeout=int(settings.gemini_timeout_seconds * 1000),
        ),
    )


def reset_client_cache() -> None:
    """Invalida el cliente cacheado (tests / rotación de key)."""
    _get_client.cache_clear()


def _generation_config() -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=_SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        temperature=0.2,
        top_p=0.95,
        max_output_tokens=1024,
    )


def _cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = _PRICING_USD_PER_1M.get(model, _DEFAULT_PRICING)
    return (input_tokens / 1_000_000) * price_in + (output_tokens / 1_000_000) * price_out


def _build_prompt(candidate: dict[str, Any], icp_text: str) -> str:
    """Prompt con candidato + ICP. Schema embebido para que Gemini lo siga."""
    schema_hint = json.dumps(CandidateFitResponse.model_json_schema(), ensure_ascii=False)
    candidate_block = json.dumps(
        {
            "full_name": candidate.get("full_name"),
            "headline": candidate.get("headline"),
            "summary": candidate.get("summary"),
        },
        ensure_ascii=False,
    )
    return (
        f"## ICP (perfil ideal)\n{icp_text}\n\n"
        f"## Candidato\n{candidate_block}\n\n"
        f"## Schema de salida (JSON estricto)\n{schema_hint}\n\n"
        "Evaluá el fit y devuelve el JSON."
    )


@retry(
    reraise=True,
    stop=stop_after_attempt(settings.llm_max_attempts),
    wait=wait_exponential_jitter(initial=0.5, max=8),
    retry=retry_if_exception(is_retryable_llm_error),
    before_sleep=log_retry_attempt,
)
async def score_candidate_fit(candidate: dict[str, Any], icp_text: str) -> ScoringResult:
    """Llama Gemini Flash para puntuar el fit candidato↔ICP."""
    client = _get_client()
    model_name = settings.default_scoring_model
    prompt = _build_prompt(candidate, icp_text)
    candidate_ref = hash_pii(candidate.get("full_name"))

    response = await client.aio.models.generate_content(
        model=model_name,
        contents=prompt,
        config=_generation_config(),
    )

    raw = response.text
    if not raw:
        raise ValueError("scoring: Gemini devolvió una respuesta vacía")
    try:
        parsed = CandidateFitResponse.model_validate_json(raw)
    except Exception as exc:
        # Sin `raw=...`: la salida cruda del LLM habla del CV de una persona.
        logger.warning(
            "scoring.invalid_json",
            model=model_name,
            candidate_ref=candidate_ref,
            error_type=type(exc).__name__,
            raw_len=len(raw),
        )
        raise

    usage = response.usage_metadata
    input_tokens = (usage.prompt_token_count or 0) if usage else 0
    output_tokens = (usage.candidates_token_count or 0) if usage else 0
    cost = _cost_usd(model_name, input_tokens, output_tokens)
    logger.debug(
        "scoring.score_candidate_fit",
        candidate_ref=candidate_ref,
        score=parsed.score,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=round(cost, 6),
    )
    return ScoringResult(
        response=parsed,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        model=model_name,
    )
