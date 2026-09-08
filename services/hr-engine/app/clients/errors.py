"""Clasificación de errores transitorios de los SDKs externos.

Contexto: los clientes reintentaban con `retry_if_exception_type((TimeoutError,
ConnectionError))` usando los BUILTINS de Python. Ninguna excepción real de
`openai` ni de `google-genai` hereda de esos builtins:

    openai.APITimeoutError    → openai.APIConnectionError → openai.APIError
    openai.RateLimitError     → openai.APIStatusError     → openai.APIError
    google.genai.errors.*     → google.genai.errors.APIError

…así que el retry NUNCA se disparaba. Acá centralizamos qué es reintentable
(timeouts, cortes de red, 429 y 5xx) y qué no (4xx de request inválido, falta
de API key, JSON inválido: reintentar no los arregla).
"""

from __future__ import annotations

import httpx
import openai
from google.genai import errors as genai_errors
from tenacity import RetryCallState

from app.monitoring import logger

#: Errores de OpenAI que sí vale la pena reintentar.
OPENAI_RETRYABLE: tuple[type[Exception], ...] = (
    openai.APITimeoutError,  # subclase de APIConnectionError
    openai.APIConnectionError,
    openai.RateLimitError,  # 429
    openai.InternalServerError,  # 5xx
)

#: Errores de transporte HTTP (los usan ambos SDKs por debajo).
HTTPX_RETRYABLE: tuple[type[Exception], ...] = (
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.RemoteProtocolError,
)

#: Códigos HTTP reintentables cuando el SDK los envuelve en su propio error.
RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})

_RETRYABLE_TYPES: tuple[type[Exception], ...] = OPENAI_RETRYABLE + HTTPX_RETRYABLE


def is_retryable_llm_error(exc: BaseException) -> bool:
    """True si el error es transitorio y conviene reintentar con backoff."""
    if isinstance(exc, _RETRYABLE_TYPES):
        return True
    if isinstance(exc, openai.APIStatusError):
        return exc.status_code in RETRYABLE_STATUS_CODES
    if isinstance(exc, genai_errors.ServerError):
        return True
    if isinstance(exc, genai_errors.APIError):
        code = getattr(exc, "code", None)
        return isinstance(code, int) and code in RETRYABLE_STATUS_CODES
    return False


def is_transient_error(exc: BaseException) -> bool:
    """Igual que `is_retryable_llm_error` + fallos de infraestructura.

    Lo usa el wrapper Celery para decidir `self.retry()` vs. fallar el run.
    """
    if is_retryable_llm_error(exc):
        return True
    # Import local: sqlalchemy/redis son pesados y esto se llama en el path de
    # error, no en el happy path.
    from redis.exceptions import ConnectionError as RedisConnectionError
    from redis.exceptions import TimeoutError as RedisTimeoutError
    from sqlalchemy.exc import DBAPIError, OperationalError

    if isinstance(exc, OperationalError | RedisConnectionError | RedisTimeoutError):
        return True
    return isinstance(exc, DBAPIError) and bool(exc.connection_invalidated)


def log_retry_attempt(retry_state: RetryCallState) -> None:
    """Callback `before_sleep` de tenacity.

    Loguea SOLO el tipo de excepción y el intento: el mensaje de error de un
    proveedor puede venir con el echo del prompt (y el prompt lleva el CV de
    una persona).
    """
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    logger.warning(
        "llm.retry",
        callable=getattr(retry_state.fn, "__name__", "unknown"),
        attempt=retry_state.attempt_number,
        error_type=type(exc).__name__ if exc else None,
    )


__all__ = [
    "HTTPX_RETRYABLE",
    "OPENAI_RETRYABLE",
    "RETRYABLE_STATUS_CODES",
    "is_retryable_llm_error",
    "is_transient_error",
    "log_retry_attempt",
]
