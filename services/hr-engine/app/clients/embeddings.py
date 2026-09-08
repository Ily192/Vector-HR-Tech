"""OpenAI text-embedding-3-small client — vector(1536) compatible.

Modelo elegido en ADR-008. text-embedding-3-small es ~$0.00002 / 1K tokens
(~$0.02 por 1M tokens). Pricing actualizado al 2026-05.

Resiliencia:
- Timeout explícito (`OPENAI_TIMEOUT_SECONDS`); el default del SDK son 600 s,
  más que el time limit de la task de Celery.
- Retries con backoff exponencial sobre las excepciones REALES del SDK
  (`app.clients.errors`), no sobre los builtins `TimeoutError`/`ConnectionError`.
- `max_retries=0` en el cliente: el retry lo maneja tenacity, no queremos el
  producto de ambos (3 x 2 = 6 llamadas pagas por operacion).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from openai import AsyncOpenAI
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.clients.errors import is_retryable_llm_error, log_retry_attempt
from app.config import settings
from app.monitoring import logger

# USD por token (input). text-embedding-3-small.
_EMBEDDING_USD_PER_1K_TOKENS = 0.00002

# Límite del modelo: 8192 tokens (~8000 chars conservador).
_MAX_INPUT_CHARS = 8000


@dataclass(slots=True, frozen=True)
class EmbeddingResult:
    vector: list[float]
    token_count: int
    cost_usd: float
    model: str


@lru_cache(maxsize=1)
def _get_client() -> AsyncOpenAI:
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY no configurada — embeddings desactivados. Setear en .env o Doppler.",
        )
    return AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout_seconds,
        max_retries=0,
    )


def reset_client_cache() -> None:
    """Invalida el cliente cacheado (tests / rotación de key)."""
    _get_client.cache_clear()


@retry(
    reraise=True,
    stop=stop_after_attempt(settings.llm_max_attempts),
    wait=wait_exponential_jitter(initial=0.5, max=8),
    retry=retry_if_exception(is_retryable_llm_error),
    before_sleep=log_retry_attempt,
)
async def embed_text(text: str, *, model: str | None = None) -> EmbeddingResult:
    """Embeber un string. Trunca a ~8000 chars (límite del modelo: 8192 tokens)."""
    if not text or not text.strip():
        raise ValueError("embed_text: input vacío")
    text_to_embed = text[:_MAX_INPUT_CHARS]
    model_name = model or settings.embedding_model
    client = _get_client()
    response = await client.embeddings.create(
        model=model_name,
        input=text_to_embed,
        encoding_format="float",
    )
    vector = response.data[0].embedding
    tokens = response.usage.total_tokens
    cost = (tokens / 1000) * _EMBEDDING_USD_PER_1K_TOKENS
    logger.debug(
        "embeddings.embed_text",
        model=model_name,
        tokens=tokens,
        cost_usd=round(cost, 6),
    )
    return EmbeddingResult(
        vector=list(vector),
        token_count=tokens,
        cost_usd=cost,
        model=model_name,
    )
