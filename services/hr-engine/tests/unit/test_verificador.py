"""El revisor de vacantes con IA (ADR-022): el veredicto, sus marcas y el adaptador de Gemini.

El cliente de Gemini es falso: aquí no se llama a la API.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from google.genai import errors, types

from app.config import settings
from app.domain.moderacion import EstadoDeModeracion, Gravedad, VacanteAModerar, decidir, evaluar
from app.domain.verificador import (
    CORREGIR,
    ESQUEMA,
    MARCA_BLOQUEADA,
    REGLA,
    SENALES,
    RevisionNoDisponibleError,
    SalidaInvalidaError,
    marcas_del_veredicto,
    veredicto_de_json,
)
from app.infrastructure import verificador_gemini as vg
from app.infrastructure.moderacion import RegistroDeIntentosRedis

TITULO = "Asesor de ventas"
DESCRIPCION = "Para empezar debes pagar el curso de inducción de 500 pesos."


def _vacante(**kw: Any) -> VacanteAModerar:
    datos: dict[str, Any] = {
        "id": uuid4(),
        "empresa_id": uuid4(),
        "titulo": TITULO,
        "descripcion": DESCRIPCION,
        "empresa_verificada": True,
        "publica_para": "propia",
        "tiene_publicadas": True,
        "duplicada": False,
        "creadas_en_la_ultima_hora": 1,
        "cuenta_nueva": False,
    }
    datos.update(kw)
    return VacanteAModerar(**datos)


def _json(
    riesgo: str, motivos: list[dict[str, str]] | None = None, senales: Any = None
) -> dict[str, Any]:
    return {"riesgo": riesgo, "motivos": motivos or [], "senales": senales or []}


# ─────────────────────────────── el veredicto ───────────────────────────────


def test_el_esquema_es_estricto_y_cubre_las_senales() -> None:
    assert ESQUEMA["additionalProperties"] is False
    assert set(ESQUEMA["required"]) == {"riesgo", "motivos", "senales"}
    assert ESQUEMA["properties"]["senales"]["items"]["enum"] == list(SENALES)
    # Cada señal concreta tiene algo que decirle a la empresa.
    assert set(SENALES) - {"otra"} <= set(CORREGIR)


def test_veredicto_valido() -> None:
    v = veredicto_de_json(
        _json("alto", [{"frase": "pagar el curso", "explicacion": "Cobra"}], ["cobro_al_candidato"])
    )
    assert v.riesgo == "alto"
    assert v.motivos[0].frase == "pagar el curso"
    assert v.senales == ("cobro_al_candidato",)


@pytest.mark.parametrize(
    "datos",
    [
        [],
        {"riesgo": "altísimo", "motivos": [], "senales": []},
        {"riesgo": "bajo", "senales": []},
        {"riesgo": "bajo", "motivos": "nada", "senales": []},
        {"riesgo": "medio", "motivos": ["texto"], "senales": []},
        {"riesgo": "medio", "motivos": [{"frase": 1, "explicacion": "x"}], "senales": []},
        {"riesgo": "medio", "motivos": [], "senales": ["inventada"]},
    ],
)
def test_veredicto_fuera_del_esquema(datos: Any) -> None:
    with pytest.raises(SalidaInvalidaError):
        veredicto_de_json(datos)


def test_riesgo_bajo_no_deja_marcas() -> None:
    v = veredicto_de_json(_json("bajo", [{"frase": "curso", "explicacion": "x"}]))
    assert marcas_del_veredicto(v, TITULO, DESCRIPCION) == []


def test_las_marcas_citan_solo_frases_que_existen() -> None:
    v = veredicto_de_json(
        _json(
            "medio",
            [
                # Sin acentos ni mayúsculas: igual aparece.
                {"frase": "PAGAR EL CURSO DE INDUCCION", "explicacion": "Cobra un curso"},
                {"frase": "deposita a la cuenta 123", "explicacion": "Inventada"},
            ],
            ["cobro_al_candidato"],
        )
    )
    marcas = marcas_del_veredicto(v, TITULO, DESCRIPCION)
    assert [m.gravedad for m in marcas] == [Gravedad.MEDIA, Gravedad.MEDIA]
    assert all(m.regla == REGLA for m in marcas)
    assert marcas[0].cita == "PAGAR EL CURSO DE INDUCCION"
    assert marcas[1].cita is None
    assert marcas[0].corregir == CORREGIR["cobro_al_candidato"]


def test_riesgo_sin_motivos_deja_una_marca_generica() -> None:
    marcas = marcas_del_veredicto(veredicto_de_json(_json("alto")), TITULO, DESCRIPCION)
    assert len(marcas) == 1
    assert marcas[0].gravedad is Gravedad.ALTA
    assert "alto" in marcas[0].senal


@pytest.mark.parametrize(
    ("riesgo", "estado"),
    [
        ("alto", EstadoDeModeracion.RECHAZADA),
        ("medio", EstadoDeModeracion.EN_REVISION),
        ("bajo", EstadoDeModeracion.PUBLICADA),
    ],
)
def test_decidir_no_cambia_con_las_marcas_de_la_ia(riesgo: str, estado: EstadoDeModeracion) -> None:
    """Una empresa verificada, sin señales en las reglas: decide lo que diga la IA."""
    v = _vacante(descripcion="Atenderás clientes en tienda. Sueldo base y prestaciones.")
    veredicto = veredicto_de_json(
        _json(riesgo, [{"frase": "Atenderás clientes", "explicacion": "x"}])
    )
    marcas = marcas_del_veredicto(veredicto, v.titulo, v.descripcion)
    assert decidir(v, evaluar(v, marcas)).estado is estado


# ─────────────────────────────── el adaptador de Gemini ───────────────────────────────


class _Modelos:
    def __init__(self, respuesta: Any = None, error: BaseException | None = None) -> None:
        self.respuesta = respuesta
        self.error = error
        self.llamadas: list[dict[str, Any]] = []

    async def generate_content(self, **kw: Any) -> Any:
        self.llamadas.append(kw)
        if self.error is not None:
            raise self.error
        return self.respuesta


class _ClienteFalso:
    def __init__(self, modelos: _Modelos) -> None:
        self.aio = SimpleNamespace(models=modelos)


def _respuesta(
    texto: str | None,
    *,
    finish: str = "STOP",
    bloqueo: str | None = None,
    entrada: int = 900,
    salida: int = 120,
    pensamiento: int = 30,
) -> Any:
    return SimpleNamespace(
        text=texto,
        candidates=[SimpleNamespace(finish_reason=types.FinishReason(finish))],
        prompt_feedback=SimpleNamespace(block_reason=bloqueo) if bloqueo else None,
        usage_metadata=SimpleNamespace(
            prompt_token_count=entrada,
            candidates_token_count=salida,
            thoughts_token_count=pensamiento,
        ),
    )


def _revisor(modelos: _Modelos, **kw: Any) -> vg.RevisorGemini:
    datos: dict[str, Any] = {
        "modelo": "gemini-3.5-flash-lite",
        "nivel": "low",
        "timeout_s": 5.0,
        "cliente": lambda: _ClienteFalso(modelos),
    }
    datos.update(kw)
    return vg.RevisorGemini(**datos)


class _Log:
    def __init__(self) -> None:
        self.eventos: list[tuple[str, dict[str, Any]]] = []

    def info(self, evento: str, **kw: Any) -> None:
        self.eventos.append((evento, kw))

    warning = info


@pytest.fixture
def log(monkeypatch: pytest.MonkeyPatch) -> _Log:
    registro = _Log()
    monkeypatch.setattr(vg, "logger", registro)
    return registro


async def test_al_modelo_solo_le_llegan_el_titulo_y_la_descripcion(log: _Log) -> None:
    modelos = _Modelos(_respuesta(json.dumps(_json("bajo"))))
    v = _vacante(publica_para="clientes", empresa_verificada=False)
    assert await _revisor(modelos).revisar(v) == []

    llamada = modelos.llamadas[0]
    assert llamada["model"] == "gemini-3.5-flash-lite"
    assert llamada["contents"] == f"Título: {TITULO}\n\nDescripción:\n{DESCRIPCION}"
    for dato in (str(v.id), str(v.empresa_id), "clientes"):
        assert dato not in llamada["contents"]
    config = llamada["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == ESQUEMA
    assert config.system_instruction == vg.INSTRUCCIONES
    assert config.thinking_config.thinking_level is types.ThinkingLevel.LOW
    # Gemini 3 ya no acepta parámetros de muestreo.
    assert config.temperature is None
    assert config.top_p is None


async def test_un_veredicto_alto_devuelve_marcas_y_registra_el_costo(log: _Log) -> None:
    salida = _json(
        "alto", [{"frase": "pagar el curso", "explicacion": "Cobra"}], ["cobro_al_candidato"]
    )
    marcas = await _revisor(_Modelos(_respuesta(json.dumps(salida)))).revisar(_vacante())
    assert [m.gravedad for m in marcas] == [Gravedad.ALTA]

    evento, datos = log.eventos[-1]
    assert evento == "moderacion.ia"
    assert datos["resultado"] == "alto"
    assert (datos["tokens_entrada"], datos["tokens_salida"], datos["tokens_razonamiento"]) == (
        900,
        120,
        30,
    )
    # 900/1M * 0.30 + (120 + 30)/1M * 2.50
    assert datos["costo_usd"] == pytest.approx(0.00027 + 0.000375)
    # Sin el texto de la vacante en el log.
    assert all(DESCRIPCION not in str(v) and TITULO not in str(v) for v in datos.values())


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError(),
        errors.ClientError(429, {"error": {"message": "Resource exhausted"}}),
        errors.ServerError(503, {"error": {"message": "Unavailable"}}),
    ],
    ids=["timeout", "429", "503"],
)
async def test_si_gemini_falla_la_revision_no_esta_disponible(
    log: _Log, error: BaseException
) -> None:
    with pytest.raises(RevisionNoDisponibleError):
        await _revisor(_Modelos(error=error)).revisar(_vacante())
    assert log.eventos[-1][0] == "moderacion.ia_fallo"


async def test_si_gemini_tarda_mas_que_el_timeout_se_corta(log: _Log) -> None:
    class Lento(_Modelos):
        async def generate_content(self, **kw: Any) -> Any:
            await asyncio.sleep(1)
            return None

    with pytest.raises(RevisionNoDisponibleError):
        await _revisor(Lento(), timeout_s=0.01).revisar(_vacante())


@pytest.mark.parametrize(
    "texto",
    ["no es json", None, json.dumps({"riesgo": "altísimo", "motivos": [], "senales": []})],
    ids=["texto", "vacio", "fuera-del-esquema"],
)
async def test_una_salida_invalida_se_reintenta(log: _Log, texto: str | None) -> None:
    with pytest.raises(RevisionNoDisponibleError):
        await _revisor(_Modelos(_respuesta(texto))).revisar(_vacante())


@pytest.mark.parametrize(
    "respuesta",
    [
        _respuesta(None, finish="SAFETY"),
        _respuesta(None, finish="PROHIBITED_CONTENT"),
        _respuesta(None, bloqueo="SAFETY"),
    ],
    ids=["finish-safety", "prohibido", "prompt-bloqueado"],
)
async def test_si_gemini_se_niega_la_vacante_va_a_revision(log: _Log, respuesta: Any) -> None:
    # Sin señales en las reglas: sin la negativa, esta vacante se publicaría.
    v = _vacante(descripcion="Atenderás clientes en tienda. Sueldo base y prestaciones.")
    marcas = await _revisor(_Modelos(respuesta)).revisar(v)
    assert marcas == [MARCA_BLOQUEADA]
    assert decidir(v, evaluar(v, marcas)).estado is EstadoDeModeracion.EN_REVISION


def test_la_configuracion_de_un_25_apaga_el_razonamiento_con_budget() -> None:
    config = vg.configuracion("gemini-2.5-flash", "low")
    assert config.thinking_config is not None
    assert config.thinking_config.thinking_budget == 0
    assert config.thinking_config.thinking_level is None


def test_un_nivel_de_razonamiento_invalido_no_arranca() -> None:
    with pytest.raises(ValueError):
        _revisor(_Modelos(), nivel="altísimo")


def test_sin_clave_o_apagado_no_hay_revisor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "google_api_key", "")
    assert vg.revisor_configurado() is None
    monkeypatch.setattr(settings, "google_api_key", "clave-de-prueba")
    monkeypatch.setattr(settings, "moderacion_ia_activa", False)
    assert vg.revisor_configurado() is None
    monkeypatch.setattr(settings, "moderacion_ia_activa", True)
    revisor = vg.revisor_configurado()
    assert isinstance(revisor, vg.RevisorGemini)


# ─────────────────────────────── el registro de intentos ───────────────────────────────


class _RedisFalso:
    def __init__(self) -> None:
        self.valores: dict[str, int] = {}
        self.vencen: dict[str, int] = {}

    def pipeline(self) -> _RedisFalso:
        self._cola: list[Any] = []
        return self

    def incr(self, clave: str) -> None:
        self._cola.append(("incr", clave))

    def expire(self, clave: str, segundos: int) -> None:
        self._cola.append(("expire", clave, segundos))

    def execute(self) -> list[Any]:
        salida: list[Any] = []
        for op in self._cola:
            if op[0] == "incr":
                self.valores[op[1]] = self.valores.get(op[1], 0) + 1
                salida.append(self.valores[op[1]])
            else:
                self.vencen[op[1]] = op[2]
                salida.append(True)
        return salida

    def delete(self, clave: str) -> None:
        self.valores.pop(clave, None)


async def test_el_registro_cuenta_por_vacante_y_vence() -> None:
    redis = _RedisFalso()
    registro = RegistroDeIntentosRedis(redis, vence_s=60)  # type: ignore[arg-type]
    v = _vacante()
    assert [await registro.sumar(v) for _ in range(3)] == [1, 2, 3]
    assert redis.vencen[registro.clave(v)] == 60
    await registro.limpiar(v)
    assert await registro.sumar(v) == 1


async def test_si_la_empresa_edita_la_vacante_la_cuenta_empieza_de_cero() -> None:
    registro = RegistroDeIntentosRedis(_RedisFalso())  # type: ignore[arg-type]
    v = _vacante()
    await registro.sumar(v)
    await registro.sumar(v)
    editada = _vacante(id=v.id, descripcion="Atenderás clientes en tienda.")
    assert await registro.sumar(editada) == 1
