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
from datetime import date
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest
from google.genai import errors as genai_errors
from google.genai import types as genai_types

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


def _genai_response(
    text: str,
    *,
    prompt_tokens: int = 1000,
    out_tokens: int = 200,
    thinking_tokens: int | None = None,
) -> Any:
    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(
            prompt_token_count=prompt_tokens,
            candidates_token_count=out_tokens,
            # El SDK devuelve None cuando el modelo no razonó.
            thoughts_token_count=thinking_tokens,
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


def test_25_flash_puntua_sin_razonar_por_defecto() -> None:
    """Razonar se cobra como salida y comparte los 1024 tokens del JSON."""
    config = scoring_mod._generation_config("gemini-2.5-flash")
    assert config.thinking_config is not None
    assert config.thinking_config.thinking_budget == settings.scoring_thinking_budget == 0
    # Los 2.x siguen aceptando temperature y top_p.
    assert config.temperature == 0.2


def test_25_pro_razona_con_su_valor_por_defecto() -> None:
    """2.5 Pro no deja apagar el razonamiento: no se le manda nada."""
    assert scoring_mod._generation_config("gemini-2.5-pro").thinking_config is None


def test_minimal_sube_a_low_donde_el_modelo_no_lo_acepta() -> None:
    """gemini-3.8-flash y los Gemini 4 no aceptan "minimal" (docs, "Thinking levels")."""
    nivel = scoring_mod.nivel_de_razonamiento
    assert nivel("gemini-3.5-flash-lite", "minimal") is genai_types.ThinkingLevel.MINIMAL
    assert nivel("gemini-3.8-flash", "minimal") is genai_types.ThinkingLevel.LOW
    assert nivel("gemini-4-hydrogen", "minimal") is genai_types.ThinkingLevel.LOW
    assert nivel("gemini-3.8-flash", "high") is genai_types.ThinkingLevel.HIGH


@pytest.mark.parametrize("modelo", ["gemini-3.5-flash-lite", "gemini-3.8-flash"])
def test_gemini_3_razona_con_thinking_level_y_sin_muestreo(modelo: str) -> None:
    """Gemini 3 usa `thinking_level` (no el budget) y ya no acepta temperature ni top_p."""
    config = scoring_mod._generation_config(modelo)
    assert config.thinking_config is not None
    assert config.thinking_config.thinking_budget is None
    assert config.thinking_config.thinking_level is not None
    assert config.thinking_config.thinking_level is scoring_mod.nivel_de_razonamiento(
        modelo, settings.scoring_thinking_level
    )
    assert config.temperature is None
    assert config.top_p is None


@pytest.mark.asyncio
async def test_el_razonamiento_se_cobra_como_salida(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _fake_genai_client([_genai_response(_VALID_SCORING_JSON, thinking_tokens=300)])
    monkeypatch.setattr(scoring_mod, "_get_client", lambda: client)
    monkeypatch.setattr(scoring_mod, "_hoy", lambda: date(2026, 11, 19))

    result = await scoring_mod._score_con_gemini({"headline": "Senior"}, "ICP Python")

    assert result.output_tokens == 500
    # gemini-3.8-flash, precio de lanzamiento: 1000/1M * 0.75 + (200 + 300)/1M * 3.75
    assert result.cost_usd == pytest.approx(0.00075 + 0.001875)


def test_default_scoring_model_is_current() -> None:
    # gemini-3.8-flash es el que pasa la prueba de sesgo de ADR-021 §9 (ADR-008).
    assert settings.default_scoring_model == "gemini-3.8-flash"
    assert not settings.default_scoring_model.startswith("gemini-2.")
    assert "1.5" not in settings.default_scoring_model


def test_el_default_razona_en_low_el_nivel_con_que_paso_el_sesgo() -> None:
    config = scoring_mod._generation_config(settings.default_scoring_model)
    assert config.thinking_config is not None
    assert config.thinking_config.thinking_level is genai_types.ThinkingLevel.LOW


@pytest.mark.parametrize(
    ("dia", "precio"),
    [
        (date(2026, 11, 19), (0.75, 3.75)),
        (date(2026, 12, 31), (0.75, 3.75)),
        (date(2027, 1, 1), (1.50, 7.50)),
    ],
)
def test_gemini_38_flash_cobra_el_precio_que_rige_ese_dia(
    dia: date, precio: tuple[float, float]
) -> None:
    """El de lanzamiento vence el 2026-12-31: el tope mensual no puede contar con él."""
    assert scoring_mod.precio_por_millon("gemini-3.8-flash", dia) == precio


def test_los_modelos_sin_precio_de_lanzamiento_no_cambian_con_la_fecha() -> None:
    for dia in (date(2026, 11, 19), date(2027, 6, 1)):
        assert scoring_mod.precio_por_millon("gemini-3.5-flash-lite", dia) == (0.30, 2.50)
        assert scoring_mod.precio_por_millon("gpt-5-mini", dia) == (0.25, 2.00)


def test_cost_usd_cobra_al_precio_de_hoy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scoring_mod, "_hoy", lambda: date(2027, 1, 1))
    # 1M de entrada y 1M de salida al precio estándar.
    assert scoring_mod.cost_usd("gemini-3.8-flash", 1_000_000, 1_000_000) == pytest.approx(9.0)


@pytest.mark.asyncio
async def test_score_candidate_fit_parses_and_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _fake_genai_client([_genai_response(_VALID_SCORING_JSON)])
    monkeypatch.setattr(scoring_mod, "_get_client", lambda: client)
    monkeypatch.setattr(scoring_mod, "_hoy", lambda: date(2026, 11, 19))

    result = await scoring_mod._score_con_gemini(
        {"full_name": "Ana Dev", "headline": "Senior", "summary": "10 años"},
        "ICP Python",
    )

    assert result.response.score == 8.0
    assert result.response.recommended_next_step == "entrevista"
    assert result.input_tokens == 1000
    # gemini-3.8-flash, precio de lanzamiento: 1000/1M * 0.75 + 200/1M * 3.75
    assert result.cost_usd == pytest.approx(0.00075 + 0.00075)
    assert result.model == "gemini-3.8-flash"


@pytest.mark.asyncio
async def test_score_candidate_fit_retries_gemini_429(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _fake_genai_client(
        [
            genai_errors.ClientError(429, {"error": {"message": "quota"}}),
            _genai_response(_VALID_SCORING_JSON),
        ],
    )
    monkeypatch.setattr(scoring_mod, "_get_client", lambda: client)

    result = await scoring_mod._score_con_gemini({"full_name": "Ana"}, "ICP")
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
        await scoring_mod._score_con_gemini(
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
        await scoring_mod._score_con_gemini({"full_name": "Ana"}, "ICP")


def test_scoring_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "google_api_key", "")
    scoring_mod.reset_client_cache()
    try:
        with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
            scoring_mod._get_client()
    finally:
        scoring_mod.reset_client_cache()
