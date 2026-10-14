"""Si un LLM deja de responder, la herramienta sigue operando.

Capas, de la más rápida a la más lenta:
1. Reintentos con backoff dentro de cada proveedor (tenacity, ya existían).
2. Respaldo en otro proveedor: Gemini → OpenAI, con el mismo SKILL.md y esquema.
3. Circuit breaker por proveedor en Redis: tras N fallos se deja de llamar.
4. Si no responde ninguno, la evaluación se APLAZA (~1 h) y luego va a revisión
   manual. La candidatura ya está guardada; nunca se pierde.

Además: los clientes async van uno por event loop (con uno cacheado, 1 de cada 2
tareas de Celery fallaba con APIConnectionError).
"""

from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
import pytest
import redis
from celery.exceptions import Retry
from openai import AsyncOpenAI

from app.clients import circuit_breaker as cb_mod
from app.clients import scoring
from app.clients.por_loop import por_event_loop
from app.clients.scoring import CandidateFitResponse, LLMUnavailableError, ScoringResult
from app.config import settings
from app.workers import cv_evaluator as cve_mod
from app.workers import run_state
from tests.unit.test_cv_evaluator import patched  # noqa: F401 - fixture

CANDIDATO = {"full_name": "Ana Dev", "headline": "Senior Python", "summary": "10 años"}


def _resultado(modelo: str) -> ScoringResult:
    return ScoringResult(
        response=CandidateFitResponse(
            score=7.5,
            rationale="Buen match con el ICP",
            gaps=[],
            strengths=["python"],
            recommended_next_step="entrevista",
        ),
        input_tokens=100,
        output_tokens=40,
        cost_usd=0.001,
        model=modelo,
    )


class _Proveedor:
    """Proveedor falso: responde, o lanza la excepción que se le indique."""

    def __init__(self, nombre: str, fallo: Exception | None = None) -> None:
        self.nombre, self.fallo, self.llamadas = nombre, fallo, 0

    async def __call__(self, _c: dict[str, Any], _icp: str) -> ScoringResult:
        self.llamadas += 1
        if self.fallo is not None:
            raise self.fallo
        return _resultado(self.nombre)


def _con_proveedores(
    monkeypatch: pytest.MonkeyPatch, gemini: _Proveedor, openai_: _Proveedor
) -> None:
    monkeypatch.setattr(scoring, "_PROVEEDORES", (("gemini", gemini), ("openai", openai_)))


def _caida() -> Exception:
    return httpx.ConnectTimeout("el proveedor no responde")


# ─── 2. Respaldo en otro proveedor ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_si_gemini_responde_no_se_toca_el_respaldo(monkeypatch: pytest.MonkeyPatch) -> None:
    gemini, openai_ = _Proveedor("gemini-2.5-flash"), _Proveedor("gpt-5-mini")
    _con_proveedores(monkeypatch, gemini, openai_)
    r = await scoring.score_candidate_fit(CANDIDATO, "ICP")
    assert r.model == "gemini-2.5-flash"
    assert openai_.llamadas == 0


@pytest.mark.asyncio
async def test_si_gemini_cae_puntua_openai_y_queda_registrado_el_modelo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gemini, openai_ = _Proveedor("gemini-2.5-flash", _caida()), _Proveedor("gpt-5-mini")
    _con_proveedores(monkeypatch, gemini, openai_)
    r = await scoring.score_candidate_fit(CANDIDATO, "ICP")
    # El modelo que puntuó viaja en el resultado: el worker lo guarda en el run.
    assert r.model == "gpt-5-mini"


@pytest.mark.asyncio
async def test_si_caen_los_dos_es_falta_de_disponibilidad(monkeypatch: pytest.MonkeyPatch) -> None:
    _con_proveedores(monkeypatch, _Proveedor("gemini", _caida()), _Proveedor("openai", _caida()))
    with pytest.raises(LLMUnavailableError):
        await scoring.score_candidate_fit(CANDIDATO, "ICP")


@pytest.mark.asyncio
async def test_un_fallo_que_no_es_caida_se_relanza_en_vez_de_aplazarse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Una respuesta inválida de Gemini no es una caída: si el respaldo tampoco
    puede, sale ESE error (fallo real), no un aplazamiento."""
    _con_proveedores(
        monkeypatch,
        _Proveedor("gemini", ValueError("JSON inválido")),
        _Proveedor("openai", _caida()),
    )
    with pytest.raises(ValueError, match="JSON inválido"):
        await scoring.score_candidate_fit(CANDIDATO, "ICP")


@pytest.mark.asyncio
async def test_el_respaldo_usa_las_mismas_instrucciones_y_valida_estricto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llamadas: list[dict[str, Any]] = []

    class _Parsed:
        def model_dump(self) -> dict[str, Any]:
            return {
                "score": 7.0,
                "rationale": "Encaja con el ICP",
                "gaps": [],
                "strengths": [],
                "recommended_next_step": "entrevista",
            }

    class _Uso:
        input_tokens, output_tokens = 1000, 200

    class _Resp:
        output_parsed = _Parsed()
        usage = _Uso()

    class _Responses:
        async def parse(self, **kw: Any) -> _Resp:
            llamadas.append(kw)
            return _Resp()

    monkeypatch.setattr(
        scoring, "_get_openai_client", lambda: type("C", (), {"responses": _Responses()})()
    )
    r = await scoring._score_con_openai(CANDIDATO, "ICP")
    assert llamadas[0]["instructions"] == scoring._system_instruction()
    assert llamadas[0]["model"] == settings.fallback_scoring_model
    assert r.model == "gpt-5-mini"
    assert r.cost_usd == pytest.approx(1000 / 1e6 * 0.25 + 200 / 1e6 * 2.00)


@pytest.mark.asyncio
async def test_una_respuesta_del_respaldo_fuera_de_rango_no_entra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Parsed:
        def model_dump(self) -> dict[str, Any]:
            return {
                "score": 42,
                "rationale": "x",
                "gaps": [],
                "strengths": [],
                "recommended_next_step": "entrevista",
            }

    class _Resp:
        output_parsed = _Parsed()
        usage = None

    class _Responses:
        async def parse(self, **_kw: Any) -> _Resp:
            return _Resp()

    monkeypatch.setattr(
        scoring, "_get_openai_client", lambda: type("C", (), {"responses": _Responses()})()
    )
    with pytest.raises(Exception, match=r"score|rationale"):
        await scoring._score_con_openai(CANDIDATO, "ICP")


# ─── 3. Circuit breaker ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tras_n_caidas_el_circuito_se_abre_y_gemini_deja_de_llamarse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gemini, openai_ = _Proveedor("gemini", _caida()), _Proveedor("gpt-5-mini")
    _con_proveedores(monkeypatch, gemini, openai_)
    for _ in range(settings.llm_breaker_umbral):
        await scoring.score_candidate_fit(CANDIDATO, "ICP")
    assert gemini.llamadas == settings.llm_breaker_umbral
    await scoring.score_candidate_fit(CANDIDATO, "ICP")
    # Circuito abierto: no se le espera más; va directo al respaldo.
    assert gemini.llamadas == settings.llm_breaker_umbral
    assert openai_.llamadas == settings.llm_breaker_umbral + 1


def test_en_el_periodo_de_prueba_un_solo_fallo_reabre(fake_redis: Any) -> None:
    breaker = cb_mod.CircuitBreaker("gemini", umbral=3)
    for _ in range(3):
        breaker.registrar_fallo()
    assert breaker.abierto()
    fake_redis.delete("llm:breaker:gemini:abierto")  # expira el enfriamiento
    assert not breaker.abierto()
    breaker.registrar_fallo()
    assert breaker.abierto()


def test_un_exito_resetea_el_contador(fake_redis: Any) -> None:
    breaker = cb_mod.CircuitBreaker("gemini", umbral=3)
    breaker.registrar_fallo()
    breaker.registrar_fallo()
    breaker.registrar_exito()
    breaker.registrar_fallo()
    breaker.registrar_fallo()
    assert not breaker.abierto()


def test_si_redis_cae_el_breaker_deja_pasar(monkeypatch: pytest.MonkeyPatch) -> None:
    class _RedisCaido:
        def __getattr__(self, _nombre: str) -> Any:
            def _falla(*_a: Any, **_kw: Any) -> Any:
                raise redis.ConnectionError("redis caído")

            return _falla

    monkeypatch.setattr(cb_mod, "_redis", lambda: _RedisCaido())
    breaker = cb_mod.CircuitBreaker("gemini")
    breaker.registrar_fallo()
    assert breaker.abierto() is False


# ─── 4. Aplazar en vez de fallar ────────────────────────────────────────────


def test_los_aplazamientos_no_superan_el_visibility_timeout() -> None:
    """Con Redis como broker, una tarea programada más allá del visibility
    timeout se entrega dos veces."""
    assert max(run_state.APLAZAMIENTOS_S) < settings.celery_visibility_timeout
    assert 50 * 60 <= sum(run_state.APLAZAMIENTOS_S) <= 90 * 60  # ~1 h de margen


@pytest.mark.asyncio
async def test_sin_llm_el_run_no_se_marca_fallido(
    monkeypatch: pytest.MonkeyPatch,
    patched: dict[str, Any],  # noqa: F811 - fixture importada
) -> None:
    async def sin_llm(_c: dict[str, Any], _icp: str) -> ScoringResult:
        raise LLMUnavailableError("ningún proveedor")

    monkeypatch.setattr(cve_mod, "score_candidate_fit", sin_llm)
    with pytest.raises(LLMUnavailableError) as info:
        await cve_mod._run(
            run_id="00000000-0000-0000-0000-000000000020",
            empresa_id="00000000-0000-0000-0000-000000000001",
            vacante_id="00000000-0000-0000-0000-0000000000aa",
            candidato_id="00000000-0000-0000-0000-0000000000bb",
        )
    assert "finish" not in patched  # ni failed ni completed: lo decide la tarea
    assert info.value.cost_usd >= 0


def _tarea_sin_llm(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    registro: list[tuple[str, dict[str, Any]]] = []

    async def _run(**_kw: Any) -> Any:
        raise LLMUnavailableError("ningún proveedor")

    async def defer_run(**kw: Any) -> None:
        registro.append(("aplazada", kw))

    async def manual(**kw: Any) -> None:
        registro.append(("revision_manual", kw))

    monkeypatch.setattr(cve_mod, "_run", _run)
    monkeypatch.setattr(run_state, "defer_run", defer_run)
    monkeypatch.setattr(run_state, "send_to_manual_review", manual)
    return registro


def test_la_tarea_se_aplaza_y_cuenta_el_aplazamiento(monkeypatch: pytest.MonkeyPatch) -> None:
    registro = _tarea_sin_llm(monkeypatch)
    cve_mod.run.push_request(called_directly=False, retries=0, is_eager=True, kwargs={})
    try:
        with pytest.raises(Retry):
            cve_mod.run(run_id="r", empresa_id="e", vacante_id="v", candidato_id="c")
    finally:
        cve_mod.run.pop_request()
    assert registro == [
        (
            "aplazada",
            {"run_id": "r", "exc": registro[0][1]["exc"], "cost_usd": 0.0, "aplazamiento": 1},
        )
    ]


def test_al_agotar_los_aplazamientos_va_a_revision_manual(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registro = _tarea_sin_llm(monkeypatch)
    cve_mod.run.push_request(called_directly=False, retries=9, is_eager=True, kwargs={})
    try:
        with pytest.raises(LLMUnavailableError):
            cve_mod.run(
                run_id="r",
                empresa_id="e",
                vacante_id="v",
                candidato_id="c",
                aplazamientos=len(run_state.APLAZAMIENTOS_S),
            )
    finally:
        cve_mod.run.pop_request()
    assert [evento for evento, _ in registro] == ["revision_manual"]


@pytest.mark.asyncio
async def test_si_caen_los_embeddings_el_cv_se_puntua_igual(
    monkeypatch: pytest.MonkeyPatch,
    patched: dict[str, Any],  # noqa: F811 - fixture importada
) -> None:
    """La vacante NO tiene embedding y el proveedor de embeddings está caído:
    antes eso tumbaba la evaluación; ahora se puntúa y el embedding queda para luego."""
    from uuid import UUID

    from app.repositories import hr as hr_repo

    llamadas_embedding = 0

    async def vacante_sin_embedding(_db: object, _id: object) -> hr_repo.VacanteRow:
        return hr_repo.VacanteRow(
            id=UUID("00000000-0000-0000-0000-0000000000aa"),
            empresa_id=UUID("00000000-0000-0000-0000-000000000001"),
            title="t",
            jd="jd",
            icp_text="icp",
            icp_embedding=None,
            status="open",
        )

    async def embeddings_caidos(_t: str, *, model: str | None = None) -> Any:
        nonlocal llamadas_embedding
        llamadas_embedding += 1
        raise _caida()

    monkeypatch.setattr(hr_repo, "get_vacante", vacante_sin_embedding)
    monkeypatch.setattr(cve_mod, "embed_text", embeddings_caidos)
    result = await cve_mod._run(
        run_id="00000000-0000-0000-0000-000000000020",
        empresa_id="00000000-0000-0000-0000-000000000001",
        vacante_id="00000000-0000-0000-0000-0000000000aa",
        candidato_id="00000000-0000-0000-0000-0000000000bb",
    )
    assert llamadas_embedding == 1  # se intentó, de verdad
    assert result["score"] == 8.5
    assert patched["finish"][-1]["status"] == "completed"


# ─── Clientes: uno por event loop ───────────────────────────────────────────


class _Embeddings(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # keep-alive, como la API real

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("content-length", 0)))
        body = json.dumps(
            {
                "object": "list",
                "model": "m",
                "data": [{"object": "embedding", "index": 0, "embedding": [0.1]}],
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            }
        ).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_a: Any) -> None:
        return None


def test_un_cliente_por_loop_aguanta_varias_tareas_seguidas() -> None:
    """Cuatro `asyncio.run` seguidos, como cuatro tareas de Celery. Con un único
    AsyncOpenAI cacheado fallaban la 2.ª y la 4.ª (medido el 2026-10-06)."""
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Embeddings)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/v1"
    cliente = por_event_loop(lambda: AsyncOpenAI(api_key="x", base_url=url, max_retries=0))

    async def tarea() -> int:
        r = await cliente().embeddings.create(model="m", input="hola")
        return len(r.data)

    try:
        assert [asyncio.run(tarea()) for _ in range(4)] == [1, 1, 1, 1]
    finally:
        srv.shutdown()


def test_los_clientes_de_llm_no_se_cachean_entre_loops() -> None:
    from app.clients import embeddings

    for get in (scoring._get_client, scoring._get_openai_client, embeddings._get_client):
        assert isinstance(get, por_event_loop)
