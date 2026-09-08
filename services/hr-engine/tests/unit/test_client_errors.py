"""Tests de la clasificación de errores reintentables.

Regresión del bug 3: los clientes reintentaban con los BUILTINS
`(TimeoutError, ConnectionError)`, y ninguna excepción real de los SDKs hereda
de ellos → el retry nunca se disparaba.
"""

from __future__ import annotations

import httpx
import openai
import pytest
from google.genai import errors as genai_errors

from app.clients.errors import is_retryable_llm_error, is_transient_error

_REQUEST = httpx.Request("POST", "https://api.example.com/v1/x")


def _response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code, request=_REQUEST)


def test_sdk_errors_are_not_builtin_timeout_or_connection_error() -> None:
    """La premisa del bug: por eso el retry viejo era decorativo."""
    assert not issubclass(openai.APITimeoutError, TimeoutError)
    assert not issubclass(openai.APIConnectionError, ConnectionError)
    assert not issubclass(openai.RateLimitError, ConnectionError | TimeoutError)
    assert not issubclass(genai_errors.APIError, ConnectionError | TimeoutError)


@pytest.mark.parametrize(
    "exc",
    [
        openai.APITimeoutError(request=_REQUEST),
        openai.APIConnectionError(request=_REQUEST),
        openai.RateLimitError("429", response=_response(429), body=None),
        openai.InternalServerError("500", response=_response(500), body=None),
        openai.APIStatusError("503", response=_response(503), body=None),
        httpx.ConnectTimeout("timeout", request=_REQUEST),
        httpx.ReadTimeout("timeout", request=_REQUEST),
        httpx.ConnectError("boom", request=_REQUEST),
        genai_errors.ServerError(503, {"error": {"message": "unavailable"}}),
        genai_errors.ClientError(429, {"error": {"message": "quota"}}),
    ],
)
def test_retryable_errors(exc: Exception) -> None:
    assert is_retryable_llm_error(exc) is True
    assert is_transient_error(exc) is True


@pytest.mark.parametrize(
    "exc",
    [
        ValueError("input inválido"),
        RuntimeError("GOOGLE_API_KEY no configurada"),
        openai.BadRequestError("400", response=_response(400), body=None),
        openai.AuthenticationError("401", response=_response(401), body=None),
        genai_errors.ClientError(400, {"error": {"message": "invalid arg"}}),
        genai_errors.ClientError(403, {"error": {"message": "forbidden"}}),
    ],
)
def test_non_retryable_errors(exc: Exception) -> None:
    assert is_retryable_llm_error(exc) is False


def test_infra_errors_are_transient_but_not_llm() -> None:
    from redis.exceptions import ConnectionError as RedisConnectionError
    from sqlalchemy.exc import OperationalError

    redis_exc = RedisConnectionError("broker caído")
    assert is_retryable_llm_error(redis_exc) is False
    assert is_transient_error(redis_exc) is True

    sa_exc = OperationalError("select 1", {}, Exception("conn reset"))
    assert is_transient_error(sa_exc) is True
