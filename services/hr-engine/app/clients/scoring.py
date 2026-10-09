"""Scoring candidato↔ICP con Gemini — structured output JSON.

Migración (2026-09): `google.generativeai` está deprecado (el propio SDK emite
aviso de fin de soporte) y `gemini-1.5-flash` es una generación retirada. Este
módulo usa el SDK vigente **`google-genai`** (`from google import genai`) y
`gemini-2.5-flash` como default.

Resiliencia:
- Timeout explícito por request (`GEMINI_TIMEOUT_SECONDS`; el SDK lo toma en ms).
- Retries sobre las excepciones reales (`google.genai.errors.ServerError`,
  `ClientError` 429, timeouts httpx) vía `app.clients.errors`.

Instrucciones: el system instruction es el cuerpo del SKILL.md de
`cv-evaluator`, cargado por `app.skills`. Antes era un texto escrito aquí a
mano que había perdido la calibración del score y la regla anti-sesgo.

Privacidad: los logs de este módulo NO llevan PII. El prompt contiene el CV de
una persona real, así que nunca logueamos `response.text` crudo ni el nombre
del candidato; usamos un hash corto (`candidate_ref`) que permite correlacionar
sin exponer identidad.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from google import genai
from google.genai import types
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.clients.circuit_breaker import CircuitBreaker
from app.clients.errors import is_retryable_llm_error, log_retry_attempt
from app.clients.por_loop import por_event_loop
from app.config import settings
from app.monitoring import hash_pii, logger
from app.skills import load_skill

#: Pricing USD por 1M tokens. Fuente: Google AI pricing (2026-09).
_PRICING_USD_PER_1M: dict[str, tuple[float, float]] = {
    # modelo: (input, output)
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-pro": (1.25, 10.00),
    # Respaldo. Fuente: OpenAI pricing, standard tier (2026-10).
    "gpt-5-mini": (0.25, 2.00),
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


#: Las reglas de puntuación —calibración del score, regla anti-sesgo, no
#: inventar experiencia— viven en el SKILL.md de cv-evaluator. Son las mismas
#: para el sourcer, que puntúa a cada candidato con esta misma función.
SCORING_SKILL = "cv-evaluator"


def _system_instruction() -> str:
    return load_skill(SCORING_SKILL).instructions


@por_event_loop
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


@por_event_loop
def _get_openai_client() -> AsyncOpenAI:
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY no configurada — no hay modelo de respaldo para el scoring."
        )
    # max_retries=0: los reintentos los hace tenacity, igual que con Gemini.
    return AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout_seconds,
        max_retries=0,
    )


def reset_client_cache() -> None:
    """Invalida los clientes cacheados (tests / rotación de key)."""
    _get_client.cache_clear()
    _get_openai_client.cache_clear()


def _generation_config() -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=_system_instruction(),
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
async def _score_con_gemini(candidate: dict[str, Any], icp_text: str) -> ScoringResult:
    """Proveedor principal: Gemini, con salida JSON."""
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


class _RespuestaOpenAI(BaseModel):
    """Esquema que se le manda a OpenAI.

    El modo estricto de Structured Outputs no admite todas las restricciones de
    JSON Schema (p. ej. `minLength`), así que aquí van sin ellas; la respuesta se
    valida después contra `CandidateFitResponse`, igual que la de Gemini.
    """

    score: float
    rationale: str
    gaps: list[str]
    strengths: list[str]
    recommended_next_step: Literal["psicometrico", "entrevista", "rechazar"]


@retry(
    reraise=True,
    stop=stop_after_attempt(settings.llm_max_attempts),
    wait=wait_exponential_jitter(initial=0.5, max=8),
    retry=retry_if_exception(is_retryable_llm_error),
    before_sleep=log_retry_attempt,
)
async def _score_con_openai(candidate: dict[str, Any], icp_text: str) -> ScoringResult:
    """Respaldo: OpenAI con las MISMAS instrucciones (el SKILL.md) y el mismo esquema.

    Responses API + `parse(text_format=...)`, la vía recomendada por la guía
    oficial de Structured Outputs.
    """
    client = _get_openai_client()
    model_name = settings.fallback_scoring_model
    response = await client.responses.parse(
        model=model_name,
        instructions=_system_instruction(),
        input=_build_prompt(candidate, icp_text),
        text_format=_RespuestaOpenAI,
    )
    if response.output_parsed is None:
        raise ValueError("scoring: OpenAI no devolvió una respuesta parseable")
    parsed = CandidateFitResponse.model_validate(response.output_parsed.model_dump())
    usage = response.usage
    input_tokens = usage.input_tokens if usage else 0
    output_tokens = usage.output_tokens if usage else 0
    return ScoringResult(
        response=parsed,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=_cost_usd(model_name, input_tokens, output_tokens),
        model=model_name,
    )


class LLMUnavailableError(RuntimeError):
    """Ningún proveedor pudo puntuar por un problema de DISPONIBILIDAD.

    Caída, timeouts, 429/5xx o circuito abierto. Es la señal para que el worker
    aplace la evaluación en vez de darla por fallida (ver workers/run_state.py).
    """

    #: Lo gastado en la ejecución antes de rendirse (lo rellena el worker).
    cost_usd: float = 0.0


#: Orden de preferencia. Cada uno con su breaker.
_PROVEEDORES = (
    ("gemini", _score_con_gemini),
    ("openai", _score_con_openai),
)


def _breaker(proveedor: str) -> CircuitBreaker:
    return CircuitBreaker(proveedor)


async def score_candidate_fit(candidate: dict[str, Any], icp_text: str) -> ScoringResult:
    """Puntúa el fit candidato↔ICP con el primer proveedor disponible.

    - Circuito abierto → se salta ese proveedor sin llamarlo.
    - Error de disponibilidad (tras sus reintentos) → cuenta para el breaker y se
      prueba el siguiente.
    - Otro error (respuesta inválida, 400) → no cuenta para el breaker, pero
      también se prueba el siguiente: lo que falla es ese modelo, no el servicio.
    - Si todos fallan por disponibilidad → `LLMUnavailableError` (se aplaza). Si
      alguno falló por otra cosa, se relanza ese error: es un fallo real.
    """
    candidate_ref = hash_pii(candidate.get("full_name"))
    otro_error: Exception | None = None
    for proveedor, puntuar in _PROVEEDORES:
        breaker = _breaker(proveedor)
        if breaker.abierto():
            logger.warning(
                "scoring.proveedor_saltado", proveedor=proveedor, motivo="circuito abierto"
            )
            continue
        try:
            resultado = await puntuar(candidate, icp_text)
        except Exception as exc:
            # RuntimeError = proveedor sin configurar (falta la key): se salta, pero
            # no es una caída, así que no cuenta para su breaker.
            sin_configurar = isinstance(exc, RuntimeError)
            disponibilidad = is_retryable_llm_error(exc) or sin_configurar
            if is_retryable_llm_error(exc):
                breaker.registrar_fallo()
            elif not sin_configurar:
                otro_error = exc
            logger.warning(
                "scoring.proveedor_fallo",
                proveedor=proveedor,
                candidate_ref=candidate_ref,
                error_type=type(exc).__name__,
                disponibilidad=disponibilidad,
            )
            continue
        breaker.registrar_exito()
        if proveedor != _PROVEEDORES[0][0]:
            logger.warning("scoring.respaldo_usado", proveedor=proveedor, model=resultado.model)
        return resultado
    if otro_error is not None:
        raise otro_error
    raise LLMUnavailableError("ningún proveedor de LLM disponible para puntuar")
