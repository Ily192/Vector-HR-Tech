"""Gemini 1.5 Flash scoring — structured output con schema Pydantic.

Default scoring model per ADR-008. Flash es ~$0.075 / 1M input tokens (≤128k),
~$0.30 / 1M output. Pricing actualizado al 2026-05.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import google.generativeai as genai
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.monitoring import logger

# Pricing per 1M tokens (Gemini 1.5 Flash, <128k context).
_GEMINI_FLASH_INPUT_USD_PER_1M = 0.075
_GEMINI_FLASH_OUTPUT_USD_PER_1M = 0.30


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


@lru_cache(maxsize=1)
def _get_model() -> genai.GenerativeModel:
    if not settings.google_api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY no configurada — scoring Gemini desactivado. "
            "Setear en .env o Doppler.",
        )
    genai.configure(api_key=settings.google_api_key)
    return genai.GenerativeModel(
        model_name=settings.default_scoring_model,
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.2,
            "top_p": 0.95,
            "max_output_tokens": 1024,
        },
        system_instruction=(
            "Sos un evaluador HR senior. Evalúa el fit candidato↔vacante con "
            "rigor. Salida ESTRICTA en JSON matching el schema. No inventes "
            "experiencia que no está en el CV. Sé conciso (rationale ≤ 300 "
            "palabras). Idioma: español neutro LATAM."
        ),
    )


def _build_prompt(candidate: dict, icp_text: str) -> str:
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
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    retry=retry_if_exception_type((TimeoutError, ConnectionError)),
)
async def score_candidate_fit(candidate: dict, icp_text: str) -> ScoringResult:
    """Llama Gemini Flash para puntuar el fit candidato↔ICP."""
    model = _get_model()
    prompt = _build_prompt(candidate, icp_text)

    response = await model.generate_content_async(prompt)
    try:
        parsed = CandidateFitResponse.model_validate_json(response.text)
    except Exception as exc:
        logger.warning(
            "scoring.invalid_json",
            error=str(exc),
            raw=response.text[:500],
        )
        raise

    usage = response.usage_metadata
    input_tokens = usage.prompt_token_count if usage else 0
    output_tokens = usage.candidates_token_count if usage else 0
    cost = (
        (input_tokens / 1_000_000) * _GEMINI_FLASH_INPUT_USD_PER_1M
        + (output_tokens / 1_000_000) * _GEMINI_FLASH_OUTPUT_USD_PER_1M
    )
    logger.debug(
        "scoring.score_candidate_fit",
        candidate=candidate.get("full_name"),
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
        model=settings.default_scoring_model,
    )
