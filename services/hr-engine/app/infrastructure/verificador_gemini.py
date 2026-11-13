"""El revisor de vacantes con Gemini (ADR-022): implementa `RevisorDeVacantes`.

Manda al modelo solo el título y la descripción de la vacante, con el prompt de
`verificador_de_vacantes.md` y salida estructurada (`app/domain/verificador.py::ESQUEMA`),
y convierte el veredicto en marcas. Es lo mismo que mide la prueba de modelos
(`app/cli/evals_verificador.py`), que importa de aquí el prompt y la configuración.

- Modelo: `MODERACION_MODELO` (por defecto `gemini-3.5-flash-lite`, el que ganó la
  prueba: 100% de las estafas graves, 0% de falsos positivos, ~US$0,0004 por vacante).
- Gemini 3 controla el razonamiento con `thinking_level` (no con `thinking_budget`)
  y ya no acepta `temperature` ni `top_p`: no se mandan.
  Fuentes: https://ai.google.dev/gemini-api/docs/thinking ("Thinking levels") y
  https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.6 ("Migrate to
  gemini-3.5-flash-lite", "API changes and parameter updates").
- Si el modelo no responde (timeout, 429, 5xx) o la salida no cumple el esquema,
  lanza `RevisionNoDisponibleError`: la vacante no se publica y el barrido la
  reintenta. Si el modelo bloquea el texto por seguridad, la vacante va a revisión
  humana (`MARCA_BLOQUEADA`).
- Cada llamada deja en el log los tokens y el costo (`moderacion.ia`), sin el texto
  de la vacante.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from google import genai
from google.genai import errors, types

from app.clients.por_loop import por_event_loop
from app.clients.scoring import cost_usd, nivel_de_razonamiento
from app.config import settings
from app.domain.moderacion import Marca, VacanteAModerar
from app.domain.verificador import (
    ESQUEMA,
    MARCA_BLOQUEADA,
    RevisionNoDisponibleError,
    SalidaInvalidaError,
    marcas_del_veredicto,
    veredicto_de_json,
)
from app.monitoring import logger

#: El prompt del revisor. Lo comparte la prueba de modelos.
INSTRUCCIONES = (
    Path(__file__).with_name("verificador_de_vacantes.md").read_text(encoding="utf-8").strip()
)

#: Tokens de salida, razonamiento incluido. La respuesta ronda los 300.
MAX_TOKENS_DE_SALIDA = 4000

#: Por qué Gemini corta una respuesta por seguridad (FinishReason) o bloquea el prompt.
_BLOQUEOS = frozenset({"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"})

_NIVELES = ("minimal", "low", "medium", "high")


def texto_de_la_vacante(titulo: str, descripcion: str) -> str:
    """Lo único que ve el modelo: ni la empresa, ni quién la publicó, ni candidatos."""
    return f"Título: {titulo}\n\nDescripción:\n{descripcion.strip()}"


def configuracion(modelo: str, nivel: str) -> types.GenerateContentConfig:
    """La misma configuración en producción y en la prueba de modelos.

    Los 2.5 (solo para comparar en la prueba) apagan el razonamiento con
    `thinking_budget=0`; los Gemini 3 usan `thinking_level`.
    """
    if modelo.startswith("gemini-2."):
        pensar = types.ThinkingConfig(thinking_budget=0)
    else:
        pensar = types.ThinkingConfig(thinking_level=nivel_de_razonamiento(modelo, nivel))
    return types.GenerateContentConfig(
        system_instruction=INSTRUCCIONES,
        response_mime_type="application/json",
        response_json_schema=ESQUEMA,
        max_output_tokens=MAX_TOKENS_DE_SALIDA,
        thinking_config=pensar,
    )


def tokens(respuesta: Any) -> tuple[int, int, int]:
    """(entrada, salida, razonamiento). La salida que se cobra incluye el razonamiento."""
    uso = getattr(respuesta, "usage_metadata", None)
    if uso is None:
        return 0, 0, 0
    entrada = getattr(uso, "prompt_token_count", 0) or 0
    pensamiento = getattr(uso, "thoughts_token_count", 0) or 0
    salida = getattr(uso, "candidates_token_count", 0) or 0
    return entrada, salida, pensamiento


def esta_bloqueada(respuesta: Any) -> bool:
    """Gemini se negó: bloqueó el prompt o cortó la respuesta por seguridad."""
    feedback = getattr(respuesta, "prompt_feedback", None)
    if feedback is not None and getattr(feedback, "block_reason", None):
        return True
    candidatos = getattr(respuesta, "candidates", None) or []
    if not candidatos:
        return False
    motivo = getattr(candidatos[0], "finish_reason", None)
    nombre = getattr(motivo, "name", None) or str(motivo or "")
    return nombre.rsplit(".", 1)[-1].upper() in _BLOQUEOS


@por_event_loop
def _cliente_gemini() -> genai.Client:
    if not settings.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY no configurada: no hay revisor de vacantes con IA.")
    return genai.Client(
        api_key=settings.google_api_key,
        # `HttpOptions.timeout` va en MILISEGUNDOS.
        http_options=types.HttpOptions(timeout=int(settings.moderacion_timeout_s * 1000)),
    )


class RevisorGemini:
    """`RevisorDeVacantes` con Gemini. Sin estado: un barrido crea uno."""

    def __init__(
        self,
        *,
        modelo: str,
        nivel: str,
        timeout_s: float,
        cliente: Callable[[], Any] = _cliente_gemini,
    ) -> None:
        if nivel not in _NIVELES:
            raise ValueError(f"thinking_level inválido: {nivel!r}")
        self._modelo = modelo
        self._nivel = nivel
        self._timeout_s = timeout_s
        self._cliente = cliente

    async def revisar(self, vacante: VacanteAModerar) -> list[Marca]:
        inicio = time.perf_counter()
        try:
            respuesta = await asyncio.wait_for(
                self._cliente().aio.models.generate_content(
                    model=self._modelo,
                    contents=texto_de_la_vacante(vacante.titulo, vacante.descripcion),
                    config=configuracion(self._modelo, self._nivel),
                ),
                timeout=self._timeout_s,
            )
        except (TimeoutError, errors.APIError, httpx.HTTPError) as exc:
            logger.warning(
                "moderacion.ia_fallo",
                vacante_id=str(vacante.id),
                modelo=self._modelo,
                error=type(exc).__name__,
                codigo=getattr(exc, "code", None),
            )
            raise RevisionNoDisponibleError(type(exc).__name__) from exc

        entrada, salida, pensamiento = tokens(respuesta)
        registro: dict[str, Any] = {
            "vacante_id": str(vacante.id),
            "modelo": self._modelo,
            "tokens_entrada": entrada,
            "tokens_salida": salida,
            "tokens_razonamiento": pensamiento,
            "costo_usd": round(cost_usd(self._modelo, entrada, salida + pensamiento), 6),
            "latencia_ms": int((time.perf_counter() - inicio) * 1000),
        }
        if esta_bloqueada(respuesta):
            logger.info("moderacion.ia", **registro, resultado="bloqueada")
            return [MARCA_BLOQUEADA]
        try:
            veredicto = veredicto_de_json(json.loads(getattr(respuesta, "text", None) or ""))
        except (ValueError, TypeError, SalidaInvalidaError) as exc:
            logger.warning("moderacion.ia", **registro, resultado="salida_invalida")
            raise RevisionNoDisponibleError("salida inválida") from exc
        logger.info("moderacion.ia", **registro, resultado=veredicto.riesgo)
        return marcas_del_veredicto(veredicto, vacante.titulo, vacante.descripcion)


def revisor_configurado() -> RevisorGemini | None:
    """El revisor si está encendido y hay clave; si no, `None` (solo reglas)."""
    if not settings.moderacion_ia_activa or not settings.google_api_key:
        return None
    return RevisorGemini(
        modelo=settings.moderacion_modelo,
        nivel=settings.moderacion_thinking_level,
        timeout_s=settings.moderacion_timeout_s,
    )
