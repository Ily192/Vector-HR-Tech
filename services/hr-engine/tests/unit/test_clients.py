"""Tests de los clientes LLM: timeouts, retries reales y ausencia de PII.

Regresiones cubiertas:
- bug 3: el retry nunca se disparaba (builtins en `retry_if_exception_type`).
- bug 4: el cliente OpenAI se creaba sin `timeout` (default del SDK: 600 s).
- bug 8: `scoring` logueaba `raw=response.text[:500]` (salida cruda del LLM
  sobre el CV de una persona) y `candidate=<nombre completo>`.
- bug 12: `google.generativeai` deprecado → `google-genai`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest
from google.genai import errors as genai_errors

from app.clients import embeddings as emb_mod
from app.clients import scoring as scoring_mod
from app.config import settings

_REQUEST = httpx.Request("POST", "https://api.example.com/v1/x")


def _rate_limit_error() -> openai.RateLimitError:
    return openai.RateLimitError(
        "429",
        response=httpx.Response(429, request=_REQUEST),
        body=None,
    )


# ── OpenAI embeddings ───────────────────────────────────────────────────────


@dataclass
class _FakeEmbeddings:
    calls: list[dict[str, Any]]
    failures: int = 0

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if len(self.calls) <= self.failures:
            raise _rate_limit_error()
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.5] * 1536)],
            usage=SimpleNamespace(total_tokens=1000),
        )


def _fake_openai_client(failures: int = 0) -> Any:
    calls: list[dict[str, Any]] = []
    return SimpleNamespace(embeddings=_FakeEmbeddings(calls=calls, failures=failures))


def test_openai_client_has_explicit_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """El default del SDK son 600 s: más que el time limit de la task."""
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    emb_mod.reset_client_cache()
    try:
        client = emb_mod._get_client()
        assert client.timeout == settings.openai_timeout_seconds
        # El retry lo hace tenacity; sin esto serían 3 x 2 = 6 llamadas pagas.
        assert client.max_retries == 0
    finally:
        emb_mod.reset_client_cache()


def test_embed_text_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openai_api_key", "")
    emb_mod.reset_client_cache()
    try:
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            emb_mod._get_client()
    finally:
        emb_mod.reset_client_cache()


@pytest.mark.asyncio
async def test_embed_text_computes_cost_and_truncates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _fake_openai_client()
    monkeypatch.setattr(emb_mod, "_get_client", lambda: client)

    result = await emb_mod.embed_text("x" * 20_000)

    assert len(result.vector) == 1536
    assert result.token_count == 1000
    assert result.cost_usd == pytest.approx(0.00002)
    assert len(client.embeddings.calls[0]["input"]) == emb_mod._MAX_INPUT_CHARS


@pytest.mark.asyncio
async def test_embed_text_retries_real_sdk_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Con los builtins viejos, este 429 NO se reintentaba nunca."""
    client = _fake_openai_client(failures=2)
    monkeypatch.setattr(emb_mod, "_get_client", lambda: client)

    result = await emb_mod.embed_text("un ICP cualquiera")

    assert result.token_count == 1000
    assert len(client.embeddings.calls) == 3  # 2 fallos + 1 éxito


@pytest.mark.asyncio
async def test_embed_text_does_not_retry_client_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    class _Boom:
        async def create(self, **_kw: Any) -> Any:
            calls.append(1)
            raise openai.BadRequestError(
                "400",
                response=httpx.Response(400, request=_REQUEST),
                body=None,
            )

    monkeypatch.setattr(emb_mod, "_get_client", lambda: SimpleNamespace(embeddings=_Boom()))

    with pytest.raises(openai.BadRequestError):
        await emb_mod.embed_text("x")
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_embed_text_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="vacío"):
        await emb_mod.embed_text("   ")


# ── Gemini scoring ──────────────────────────────────────────────────────────

_VALID_SCORING_JSON = json.dumps(
    {
        "score": 8.0,
        "rationale": "Coincide en stack y seniority requerido",
        "gaps": ["sin inglés C1"],
        "strengths": ["python"],
        "recommended_next_step": "entrevista",
    },
)


class _FakeModels:
    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _fake_genai_client(responses: list[Any]) -> Any:
    models = _FakeModels(responses)
    return SimpleNamespace(aio=SimpleNamespace(models=models))


def _genai_response(text: str, *, prompt_tokens: int = 1000, out_tokens: int = 200) -> Any:
    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(
            prompt_token_count=prompt_tokens,
            candidates_token_count=out_tokens,
        ),
    )


def test_gemini_client_uses_current_sdk_and_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """`google-genai` (no `google.generativeai`) + timeout en milisegundos."""
    monkeypatch.setattr(settings, "google_api_key", "gk-test")
    scoring_mod.reset_client_cache()
    try:
        client = scoring_mod._get_client()
        assert type(client).__module__.startswith("google.genai")
        assert client._api_client._http_options.timeout == int(
            settings.gemini_timeout_seconds * 1000,
        )
    finally:
        scoring_mod.reset_client_cache()


def test_default_scoring_model_is_current() -> None:
    assert settings.default_scoring_model == "gemini-2.5-flash"
    assert "1.5" not in settings.default_scoring_model


@pytest.mark.asyncio
async def test_score_candidate_fit_parses_and_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _fake_genai_client([_genai_response(_VALID_SCORING_JSON)])
    monkeypatch.setattr(scoring_mod, "_get_client", lambda: client)

    result = await scoring_mod.score_candidate_fit(
        {"full_name": "Ana Dev", "headline": "Senior", "summary": "10 años"},
        "ICP Python",
    )

    assert result.response.score == 8.0
    assert result.response.recommended_next_step == "entrevista"
    assert result.input_tokens == 1000
    # 1000/1M * 0.30 + 200/1M * 2.50
    assert result.cost_usd == pytest.approx(0.0003 + 0.0005)
    assert result.model == "gemini-2.5-flash"


@pytest.mark.asyncio
async def test_score_candidate_fit_retries_gemini_429(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _fake_genai_client(
        [
            genai_errors.ClientError(429, {"error": {"message": "quota"}}),
            _genai_response(_VALID_SCORING_JSON),
        ],
    )
    monkeypatch.setattr(scoring_mod, "_get_client", lambda: client)

    result = await scoring_mod.score_candidate_fit({"full_name": "Ana"}, "ICP")
    assert result.response.score == 8.0
    assert len(client.aio.models.calls) == 2


@pytest.mark.asyncio
async def test_invalid_json_log_does_not_leak_pii(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ni `raw=<salida del LLM>` ni `candidate=<nombre completo>` en los logs."""
    cv_text = "Ana Dev — DNI 12345678, ana@example.com, 10 años en Python"
    client = _fake_genai_client([_genai_response(f"no soy json: {cv_text}")])
    monkeypatch.setattr(scoring_mod, "_get_client", lambda: client)

    with caplog.at_level("WARNING"), pytest.raises(Exception, match="valid"):
        await scoring_mod.score_candidate_fit(
            {"full_name": "Ana Dev", "summary": cv_text},
            "ICP",
        )

    logged = caplog.text
    assert "scoring.invalid_json" in logged
    assert "Ana Dev" not in logged
    assert "12345678" not in logged
    assert "ana@example.com" not in logged
    assert "candidate_ref" in logged


@pytest.mark.asyncio
async def test_empty_gemini_response_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _fake_genai_client([_genai_response("")])
    monkeypatch.setattr(scoring_mod, "_get_client", lambda: client)
    with pytest.raises(ValueError, match="vacía"):
        await scoring_mod.score_candidate_fit({"full_name": "Ana"}, "ICP")


def test_scoring_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "google_api_key", "")
    scoring_mod.reset_client_cache()
    try:
        with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
            scoring_mod._get_client()
    finally:
        scoring_mod.reset_client_cache()
