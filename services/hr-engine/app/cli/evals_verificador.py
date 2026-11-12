"""Compara modelos para el verificador de vacantes (PR 3) con un set sintético.

    python -m app.cli.evals_verificador                     # los Gemini por defecto
    python -m app.cli.evals_verificador --modelos gemini-3.5-flash-lite gemini-2.5-flash-lite
    python -m app.cli.evals_verificador --con-claude        # suma Haiku, Sonnet y Opus 5.5
    python -m app.cli.evals_verificador --var-local C:/ruta/var-local.env --tope-usd 1

Por defecto corre gemini-2.5-flash (el que usa hoy el hr-engine para los CVs),
gemini-3.5-flash-lite (el Flash-Lite vigente) y gemini-3.8-flash. Los de Claude están
listos pero apagados: hoy no hay créditos en la API de Anthropic (`--con-claude`).

Lee `evals/verificador/casos.yaml` (40 vacantes inventadas: 22 legítimas, 13 de riesgo
alto y 5 de riesgo medio) y `evals/verificador/instrucciones.md` (el prompt, igual para
todos los modelos). Manda cada vacante a cada modelo con salida estructurada y escribe
`evals/verificador/RESULTADOS.md` (tabla, fallos y recomendación) y el detalle en
`evals/verificador/resultados/<fecha>.json`, que git ignora.

Credenciales: ANTHROPIC_API_KEY y GOOGLE_API_KEY (o GEMINI_API_KEY) del entorno o, si
faltan, de `var-local.env` (por defecto en la raíz del repo; `--var-local` o
`VAR_LOCAL_ENV` para otra ruta). Nunca se imprimen. Un modelo sin credencial no se
corre y queda anotado. Corta si el gasto acumulado pasa de `--tope-usd` (2 por
defecto). Sale con 0 si corrió al menos un modelo, 2 si no se pudo correr ninguno.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml

#: Raíz del repo (services/hr-engine/app/cli → raíz).
RAIZ = Path(__file__).resolve().parents[4]
DIRECTORIO = RAIZ / "evals" / "verificador"

RIESGOS = ("bajo", "medio", "alto")

#: Las categorías que puede devolver el modelo (enum del esquema).
SENALES = (
    "cobro_al_candidato",
    "datos_sensibles_anticipados",
    "inversion_o_multinivel",
    "mula_de_dinero",
    "actividad_ilegal",
    "posible_trata",
    "estafa_de_tareas",
    "suplantacion_de_marca",
    "contacto_solo_mensajeria",
    "enlace_acortado",
    "sueldo_irreal",
    "oportunidad_vaga",
    "otra",
)

ESQUEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "riesgo": {"type": "string", "enum": list(RIESGOS)},
        "motivos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "frase": {"type": "string"},
                    "explicacion": {"type": "string"},
                },
                "required": ["frase", "explicacion"],
                "additionalProperties": False,
            },
        },
        "senales": {"type": "array", "items": {"type": "string", "enum": list(SENALES)}},
    },
    "required": ["riesgo", "motivos", "senales"],
    "additionalProperties": False,
}

#: Precios de Claude: skill claude-api (tabla "Current Models", cacheada 2026-11-03).
FUENTE_CLAUDE = "skill claude-api, tabla Current Models (2026-11-03)"
#: Precios de Gemini: nivel de pago, texto.
FUENTE_GEMINI = "https://ai.google.dev/gemini-api/docs/pricing"

BETA_FALLBACK = "server-side-fallback-2026-07-01"
MAX_TOKENS = 4000


@dataclass(frozen=True, slots=True)
class Modelo:
    id: str
    proveedor: Literal["anthropic", "google"]
    #: USD por millón de tokens.
    precio_entrada: float
    precio_salida: float
    fuente_precio: str
    #: Fallback del lado del servidor (Opus 5.5 y Sonnet 5.5; Haiku 5.5 no lo tiene).
    con_fallback: bool = False
    #: Gemini 2.5 usa `thinking_budget`; Gemini 3 en adelante, `thinking_level`.
    pensamiento: Literal["adaptativo", "budget_0", "level_low"] = "adaptativo"
    nota: str = ""
    #: Entra en la corrida sin `--modelos`. Los de Claude, además, piden `--con-claude`.
    por_defecto: bool = True


MODELOS: tuple[Modelo, ...] = (
    Modelo("claude-haiku-5-5", "anthropic", 0.10, 0.50, FUENTE_CLAUDE),
    Modelo("claude-sonnet-5-5", "anthropic", 2.00, 10.00, FUENTE_CLAUDE, con_fallback=True),
    Modelo("claude-opus-5-5", "anthropic", 4.00, 20.00, FUENTE_CLAUDE, con_fallback=True),
    Modelo(
        "gemini-2.5-flash",
        "google",
        0.30,
        2.50,
        FUENTE_GEMINI,
        pensamiento="budget_0",
        nota="el del hr-engine hoy; deprecado, desde el 2026-12-01 se redirige a 3.5 Flash-Lite",
    ),
    Modelo(
        "gemini-3.5-flash-lite",
        "google",
        0.30,
        2.50,
        FUENTE_GEMINI,
        pensamiento="level_low",
        nota="el Flash-Lite vigente y el reemplazo oficial de 2.5 Flash",
    ),
    Modelo(
        "gemini-3.8-flash",
        "google",
        0.75,
        3.75,
        FUENTE_GEMINI,
        pensamiento="level_low",
        nota="el Flash más nuevo; sube a US$1,50 / US$7,50 desde el 2027-01-01",
    ),
    Modelo(
        "gemini-2.5-flash-lite",
        "google",
        0.10,
        0.40,
        FUENTE_GEMINI,
        pensamiento="budget_0",
        nota="no deprecado, pero la API solo lo da a quien ya lo usaba; solo con --modelos",
        por_defecto=False,
    ),
)

PRECIOS = {m.id: m for m in MODELOS}


# ─── Casos ───────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Caso:
    id: str
    pais: str
    esperado: str
    senal: str
    titulo: str
    descripcion: str

    def texto(self) -> str:
        return f"Título: {self.titulo}\n\nDescripción:\n{self.descripcion.strip()}"


class SetInvalidoError(ValueError):
    """El `casos.yaml` no sirve para medir."""


def cargar_casos(archivo: Path) -> list[Caso]:
    datos = yaml.safe_load(archivo.read_text(encoding="utf-8")) or {}
    casos, problemas, vistos = [], [], set()
    for i, c in enumerate(datos.get("casos") or [], start=1):
        ident = str(c.get("id") or f"#{i}")
        if ident in vistos:
            problemas.append(f"{ident}: id repetido")
        vistos.add(ident)
        if c.get("esperado") not in RIESGOS:
            problemas.append(f"{ident}: esperado tiene que ser bajo, medio o alto")
            continue
        if not c.get("titulo") or not c.get("descripcion"):
            problemas.append(f"{ident}: falta el título o la descripción")
            continue
        casos.append(
            Caso(
                id=ident,
                pais=str(c.get("pais") or ""),
                esperado=c["esperado"],
                senal=str(c.get("senal") or ""),
                titulo=str(c["titulo"]).strip(),
                descripcion=str(c["descripcion"]),
            )
        )
    if not casos and not problemas:
        problemas.append("casos.yaml no trae casos")
    if problemas:
        raise SetInvalidoError("\n".join(problemas))
    return casos


# ─── Credenciales ────────────────────────────────────────────────────────

CLAVES = ("ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY")


def cargar_credenciales(archivo: Path | None) -> None:
    """Completa el entorno del proceso con las claves de `archivo` que falten.

    No pisa lo que ya está en el entorno y no imprime nada.
    """
    if archivo is None or not archivo.is_file():
        return
    for linea in archivo.read_text(encoding="utf-8-sig").splitlines():
        m = re.match(r"\s*(?:export\s+)?([A-Z_]+)\s*=\s*(.*?)\s*$", linea)
        if not m or m.group(1) not in CLAVES or os.environ.get(m.group(1)):
            continue
        valor = m.group(2).strip().strip('"').strip("'")
        if valor:
            os.environ[m.group(1)] = valor


def clave_de_gemini() -> str | None:
    return os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or None


def tiene_credencial(modelo: Modelo) -> bool:
    if modelo.proveedor == "anthropic":
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    return clave_de_gemini() is not None


# ─── Respuestas ──────────────────────────────────────────────────────────


@dataclass(slots=True)
class Resultado:
    caso: str
    esperado: str
    modelo: str
    riesgo: str | None = None
    #: El modelo se negó (`stop_reason == "refusal"`): va a revisión manual.
    rechazo: bool = False
    error: str | None = None
    motivos: list[dict[str, str]] = field(default_factory=list)
    senales: list[str] = field(default_factory=list)
    costo_usd: float = 0.0
    latencia_s: float = 0.0
    tokens_entrada: int = 0
    tokens_salida: int = 0
    servido_por: str | None = None

    @property
    def decision(self) -> str | None:
        """Lo que haría la plataforma: un rechazo del modelo cuenta como revisión (medio)."""
        if self.error is not None:
            return None
        return "medio" if self.rechazo else self.riesgo


def costo_claude(modelo: Modelo, uso: Any) -> float:
    entrada = getattr(uso, "input_tokens", 0) or 0
    escritura = getattr(uso, "cache_creation_input_tokens", 0) or 0
    lectura = getattr(uso, "cache_read_input_tokens", 0) or 0
    salida = getattr(uso, "output_tokens", 0) or 0
    return (
        (entrada + 1.25 * escritura + 0.1 * lectura) * modelo.precio_entrada
        + salida * modelo.precio_salida
    ) / 1_000_000


def costo_gemini(modelo: Modelo, entrada: int, salida: int) -> float:
    return (entrada * modelo.precio_entrada + salida * modelo.precio_salida) / 1_000_000


def interpretar_json(texto: str) -> tuple[str, list[dict[str, str]], list[str]]:
    datos = json.loads(texto)
    riesgo = datos.get("riesgo")
    if riesgo not in RIESGOS:
        raise ValueError(f"riesgo inválido: {riesgo!r}")
    motivos = [
        {"frase": str(m.get("frase", "")), "explicacion": str(m.get("explicacion", ""))}
        for m in datos.get("motivos") or []
    ]
    senales = [str(s) for s in datos.get("senales") or []]
    return riesgo, motivos, senales


def leer_respuesta_claude(modelo: Modelo, caso: Caso, respuesta: Any, latencia: float) -> Resultado:
    """Convierte la respuesta de la API de Claude en un `Resultado`."""
    servido = getattr(respuesta, "model", None) or modelo.id
    precio = PRECIOS.get(servido, modelo)
    uso = getattr(respuesta, "usage", None)
    r = Resultado(
        caso=caso.id,
        esperado=caso.esperado,
        modelo=modelo.id,
        costo_usd=costo_claude(precio, uso) if uso is not None else 0.0,
        latencia_s=latencia,
        tokens_entrada=(getattr(uso, "input_tokens", 0) or 0) if uso is not None else 0,
        tokens_salida=(getattr(uso, "output_tokens", 0) or 0) if uso is not None else 0,
        servido_por=servido,
    )
    motivo = getattr(respuesta, "stop_reason", None)
    if motivo == "refusal":
        r.rechazo = True
        return r
    if motivo == "max_tokens":
        r.error = "max_tokens: la respuesta quedó cortada"
        return r
    texto = next((b.text for b in respuesta.content if getattr(b, "type", None) == "text"), None)
    if texto is None:
        r.error = f"sin bloque de texto (stop_reason={motivo})"
        return r
    try:
        r.riesgo, r.motivos, r.senales = interpretar_json(texto)
    except (ValueError, AttributeError) as exc:
        r.error = f"JSON inválido: {type(exc).__name__}"
    return r


def leer_respuesta_gemini(modelo: Modelo, caso: Caso, respuesta: Any, latencia: float) -> Resultado:
    uso = getattr(respuesta, "usage_metadata", None)
    entrada = (getattr(uso, "prompt_token_count", 0) or 0) if uso else 0
    pensamiento = (getattr(uso, "thoughts_token_count", 0) or 0) if uso else 0
    salida = ((getattr(uso, "candidates_token_count", 0) or 0) if uso else 0) + pensamiento
    r = Resultado(
        caso=caso.id,
        esperado=caso.esperado,
        modelo=modelo.id,
        costo_usd=costo_gemini(modelo, entrada, salida),
        latencia_s=latencia,
        tokens_entrada=entrada,
        tokens_salida=salida,
        servido_por=modelo.id,
    )
    texto = getattr(respuesta, "text", None)
    if not texto:
        motivo = None
        candidatos = getattr(respuesta, "candidates", None) or []
        if candidatos:
            motivo = getattr(candidatos[0], "finish_reason", None)
        if str(motivo).upper().endswith("SAFETY"):
            r.rechazo = True
        else:
            r.error = f"sin texto (finish_reason={motivo})"
        return r
    try:
        r.riesgo, r.motivos, r.senales = interpretar_json(texto)
    except (ValueError, AttributeError) as exc:
        r.error = f"JSON inválido: {type(exc).__name__}"
    return r


# ─── Llamadas ────────────────────────────────────────────────────────────


class Presupuesto:
    def __init__(self, tope_usd: float) -> None:
        self.tope_usd = tope_usd
        self.gastado = 0.0

    @property
    def agotado(self) -> bool:
        return self.gastado >= self.tope_usd

    def sumar(self, costo: float) -> None:
        self.gastado += costo


async def _llamar_claude(cliente: Any, modelo: Modelo, instrucciones: str, caso: Caso) -> Resultado:
    import anthropic

    pedido: dict[str, Any] = {
        "model": modelo.id,
        "max_tokens": MAX_TOKENS,
        "system": instrucciones,
        "messages": [{"role": "user", "content": caso.texto()}],
        "thinking": {"type": "adaptive"},
        "output_config": {
            "effort": "low",
            "format": {"type": "json_schema", "schema": ESQUEMA},
        },
    }
    inicio = time.perf_counter()
    try:
        if modelo.con_fallback:
            respuesta = await cliente.beta.messages.create(
                **pedido, betas=[BETA_FALLBACK], fallbacks="default"
            )
        else:
            respuesta = await cliente.messages.create(**pedido)
    except anthropic.APIStatusError as exc:
        return Resultado(caso.id, caso.esperado, modelo.id, error=f"API {exc.status_code}")
    except anthropic.APIConnectionError as exc:
        return Resultado(caso.id, caso.esperado, modelo.id, error=type(exc).__name__)
    return leer_respuesta_claude(modelo, caso, respuesta, time.perf_counter() - inicio)


async def _llamar_gemini(cliente: Any, modelo: Modelo, instrucciones: str, caso: Caso) -> Resultado:
    from google.genai import errors, types

    if modelo.pensamiento == "budget_0":
        pensar = types.ThinkingConfig(thinking_budget=0)
    elif modelo.pensamiento == "level_low":
        pensar = types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)
    else:
        pensar = None
    config = types.GenerateContentConfig(
        system_instruction=instrucciones,
        response_mime_type="application/json",
        response_json_schema=ESQUEMA,
        max_output_tokens=MAX_TOKENS,
        thinking_config=pensar,
    )
    inicio = time.perf_counter()
    try:
        respuesta = await cliente.aio.models.generate_content(
            model=modelo.id, contents=caso.texto(), config=config
        )
    except errors.APIError as exc:
        return Resultado(caso.id, caso.esperado, modelo.id, error=f"API {exc.code}")
    return leer_respuesta_gemini(modelo, caso, respuesta, time.perf_counter() - inicio)


async def correr_modelo(
    modelo: Modelo,
    casos: Sequence[Caso],
    instrucciones: str,
    presupuesto: Presupuesto,
    *,
    concurrencia: int = 4,
) -> tuple[list[Resultado], bool]:
    """Corre un modelo sobre todos los casos. Devuelve los resultados y si lo cortó el tope."""
    if modelo.proveedor == "anthropic":
        import anthropic

        cliente: Any = anthropic.AsyncAnthropic(max_retries=3, timeout=120.0)
        llamar = _llamar_claude
    else:
        from google import genai
        from google.genai import types

        cliente = genai.Client(
            api_key=clave_de_gemini(), http_options=types.HttpOptions(timeout=120_000)
        )
        llamar = _llamar_gemini

    semaforo = asyncio.Semaphore(concurrencia)
    cortado = False

    async def uno(caso: Caso) -> Resultado | None:
        nonlocal cortado
        async with semaforo:
            if presupuesto.agotado:
                cortado = True
                return None
            r = await llamar(cliente, modelo, instrucciones, caso)
            presupuesto.sumar(r.costo_usd)
            return r

    resultados = await asyncio.gather(*(uno(c) for c in casos))
    return [r for r in resultados if r is not None], cortado


# ─── Métricas ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Metricas:
    modelo: str
    casos: int
    corridos: int
    errores: int
    rechazos: int
    recall_alto: float | None
    #: Sospechosas (medio o alto) que el modelo dejó como bajo: pasarían sin revisión.
    estafas_como_bajo: int
    falsos_positivos: float | None
    exactitud: float | None
    costo_total: float
    costo_por_vacante: float | None
    latencia_media: float | None


def metricas(modelo: str, total_casos: int, resultados: Iterable[Resultado]) -> Metricas:
    rs = list(resultados)
    validos = [r for r in rs if r.decision is not None]
    altos = [r for r in validos if r.esperado == "alto"]
    legitimas = [r for r in validos if r.esperado == "bajo"]
    costo = sum(r.costo_usd for r in rs)
    con_latencia = [r.latencia_s for r in validos if r.latencia_s > 0]
    return Metricas(
        modelo=modelo,
        casos=total_casos,
        corridos=len(rs),
        errores=sum(r.error is not None for r in rs),
        rechazos=sum(r.rechazo for r in rs),
        recall_alto=(sum(r.decision == "alto" for r in altos) / len(altos)) if altos else None,
        estafas_como_bajo=sum(r.esperado != "bajo" and r.decision == "bajo" for r in validos),
        falsos_positivos=(
            sum(r.decision != "bajo" for r in legitimas) / len(legitimas) if legitimas else None
        ),
        exactitud=(sum(r.decision == r.esperado for r in validos) / len(validos))
        if validos
        else None,
        costo_total=costo,
        costo_por_vacante=(costo / len(rs)) if rs else None,
        latencia_media=(sum(con_latencia) / len(con_latencia)) if con_latencia else None,
    )


#: Para recomendar: ninguna estafa de alto puede quedar abajo de alto, ninguna
#: sospechosa puede pasar como bajo y como mucho 1 de cada 10 legítimas a revisión.
MAX_FALSOS_POSITIVOS = 0.10


def recomendar(todas: Iterable[Metricas]) -> tuple[Metricas | None, str]:
    completas = [m for m in todas if m.corridos == m.casos and m.errores == 0]
    aptas = [
        m
        for m in completas
        if m.recall_alto == 1.0
        and m.estafas_como_bajo == 0
        and m.falsos_positivos is not None
        and m.falsos_positivos <= MAX_FALSOS_POSITIVOS
    ]
    if aptas:
        elegido = min(aptas, key=lambda m: (m.costo_por_vacante or 0.0, m.modelo))
        return elegido, (
            f"{elegido.modelo}: el más barato que detectó todas las de riesgo alto, no dejó "
            f"pasar ninguna sospechosa como bajo y mandó a revisión el "
            f"{_pct(elegido.falsos_positivos)} de las legítimas."
        )
    if not completas:
        return None, "Ningún modelo corrió el set completo: no hay recomendación todavía."
    mejor = max(completas, key=lambda m: (m.recall_alto or 0.0, -(m.falsos_positivos or 1.0)))
    return None, (
        "Ningún modelo cumplió el criterio (recall de alto 100%, ninguna sospechosa como "
        f"bajo, falsos positivos ≤ {_pct(MAX_FALSOS_POSITIVOS)}). El más cercano fue "
        f"{mejor.modelo} (recall de alto {_pct(mejor.recall_alto)}, falsos positivos "
        f"{_pct(mejor.falsos_positivos)})."
    )


# ─── Informe ─────────────────────────────────────────────────────────────


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{round(x * 100)}%"


def _usd(x: float | None, decimales: int = 5) -> str:
    return "—" if x is None else f"US${x:.{decimales}f}"


def estimar_costo(modelo: Modelo, casos: Sequence[Caso], instrucciones: str) -> float:
    """Estimación sin llamar a la API: ~3,5 caracteres por token y ~300 de salida."""
    entrada = sum((len(instrucciones) + len(c.texto()) + 600) / 3.5 for c in casos)
    salida = 300 * len(casos)
    return (entrada * modelo.precio_entrada + salida * modelo.precio_salida) / 1_000_000


def informe_markdown(
    *,
    fecha: datetime,
    casos: Sequence[Caso],
    instrucciones: str,
    metricas_por_modelo: Sequence[Metricas],
    resultados: Sequence[Resultado],
    sin_correr: dict[str, str],
    gastado: float,
    tope: float,
) -> str:
    por_clase = {r: sum(c.esperado == r for c in casos) for r in RIESGOS}
    lineas = [
        "# Verificador de vacantes: comparación de modelos",
        "",
        f"Corrida del {fecha:%Y-%m-%d %H:%M} UTC con `python -m app.cli.evals_verificador` "
        f"(services/hr-engine). Set sintético `casos.yaml`: {len(casos)} vacantes inventadas "
        f"de México y Venezuela ({por_clase['bajo']} legítimas, {por_clase['alto']} de riesgo "
        f"alto y {por_clase['medio']} de riesgo medio). Mismo prompt para todos "
        "(`instrucciones.md`), salida estructurada con el esquema del script y una sola "
        "pasada por modelo.",
        "",
        "- Claude: `thinking` adaptativo, `effort: low`, `output_config.format`. Opus 5.5 y "
        f'Sonnet 5.5 con `fallbacks: "default"` (beta `{BETA_FALLBACK}`); Haiku 5.5 no '
        "tiene fallback del lado del servidor y su negativa cuenta como revisión manual.",
        "- Gemini: `generate_content` con `response_json_schema`; 2.5 con `thinking_budget=0` "
        "(como el hr-engine hoy) y los 3.x con `thinking_level=LOW`.",
        "- Los modelos de Claude están listos en el script pero apagados por defecto "
        "(`--con-claude`): hoy no hay créditos en la API de Anthropic.",
        "",
        "Criterio: el más barato con recall de alto = 100%, ninguna sospechosa como bajo "
        f"y falsos positivos ≤ {_pct(MAX_FALSOS_POSITIVOS)}.",
        "",
        "## Resultados",
        "",
    ]
    if metricas_por_modelo:
        lineas += [
            "| Modelo | Recall alto | Sospechosas como bajo | Falsos positivos | Exactitud "
            "| Negativas | Errores | Costo por vacante | Costo total | Latencia media |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for m in metricas_por_modelo:
            latencia = "—" if m.latencia_media is None else f"{m.latencia_media:.1f} s"
            corridos = "" if m.corridos == m.casos else f" ({m.corridos}/{m.casos})"
            lineas.append(
                f"| `{m.modelo}`{corridos} | {_pct(m.recall_alto)} | {m.estafas_como_bajo} "
                f"| {_pct(m.falsos_positivos)} | {_pct(m.exactitud)} | {m.rechazos} "
                f"| {m.errores} | {_usd(m.costo_por_vacante)} | {_usd(m.costo_total, 4)} "
                f"| {latencia} |"
            )
    else:
        lineas.append("Todavía no corrió ningún modelo.")
    if sin_correr:
        lineas += ["", "Sin correr:"]
        lineas += [f"- `{k}`: {v}" for k, v in sin_correr.items()]
    lineas += ["", f"Gasto de la corrida: {_usd(gastado, 4)} (tope {_usd(tope, 2)})."]

    _, texto = recomendar(metricas_por_modelo)
    lineas += ["", "## Recomendación", "", texto]

    fallos = [r for r in resultados if r.decision != r.esperado]
    if fallos:
        lineas += ["", "## Fallos por modelo", ""]
        senal = {c.id: c.senal for c in casos}
        for m in metricas_por_modelo:
            propios = [r for r in fallos if r.modelo == m.modelo]
            if not propios:
                continue
            lineas.append(f"### `{m.modelo}`")
            lineas.append("")
            for r in sorted(propios, key=lambda x: x.caso):
                obtenido = (
                    f"error ({r.error})"
                    if r.error
                    else ("negativa → revisión" if r.rechazo else r.riesgo)
                )
                frase = f" · cita: «{r.motivos[0]['frase'][:90]}»" if r.motivos else ""
                lineas.append(
                    f"- `{r.caso}`: esperado {r.esperado}, obtuvo {obtenido}. "
                    f"Señal: {senal.get(r.caso, '')}{frase}"
                )
            lineas.append("")

    lineas += ["", "## Estimación antes de correr", ""]
    lineas.append(
        "| Modelo | Precio (entrada / salida por millón) | Estimado para el set | Fuente |"
    )
    lineas.append("|---|---|---|---|")
    for modelo in MODELOS:
        nota = f" {modelo.nota}." if modelo.nota else ""
        lineas.append(
            f"| `{modelo.id}` | US${modelo.precio_entrada:.2f} / US${modelo.precio_salida:.2f} "
            f"| ~{_usd(estimar_costo(modelo, casos, instrucciones), 3)} | "
            f"{modelo.fuente_precio}.{nota} |"
        )
    return "\n".join(lineas).rstrip() + "\n"


# ─── Entrada ─────────────────────────────────────────────────────────────


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli.evals_verificador",
        description="Compara modelos para el verificador de vacantes con un set sintético.",
    )
    parser.add_argument(
        "--modelos", nargs="+", choices=[m.id for m in MODELOS], help="por defecto, todos"
    )
    parser.add_argument("--dir", default=str(DIRECTORIO), help="directorio del set")
    parser.add_argument(
        "--var-local",
        default=os.environ.get("VAR_LOCAL_ENV") or str(RAIZ / "var-local.env"),
        help="archivo con las claves si no están en el entorno",
    )
    parser.add_argument("--tope-usd", type=float, default=2.0, help="corta al pasar este gasto")
    parser.add_argument("--concurrencia", type=int, default=4)
    parser.add_argument(
        "--con-claude",
        action="store_true",
        help="incluye los modelos de Claude (apagados por defecto: no hay créditos de Anthropic)",
    )
    return parser.parse_args(argv)


def elegir_modelos(
    pedidos: Sequence[str] | None, *, con_claude: bool
) -> tuple[list[Modelo], dict[str, str]]:
    """Los modelos a correr y los que quedan fuera por la bandera de Claude."""
    base = [m for m in MODELOS if (m.id in pedidos if pedidos else m.por_defecto)]
    if con_claude:
        return base, {}
    fuera = {
        m.id: "apagado: sin créditos en la API de Anthropic (se activa con --con-claude)"
        for m in base
        if m.proveedor == "anthropic"
    }
    return [m for m in base if m.proveedor != "anthropic"], fuera


async def _correr(
    modelos: Sequence[Modelo],
    casos: Sequence[Caso],
    instrucciones: str,
    presupuesto: Presupuesto,
    concurrencia: int,
) -> tuple[list[Metricas], list[Resultado], dict[str, str]]:
    todas, resultados, sin_correr = [], [], {}
    for modelo in modelos:
        if not tiene_credencial(modelo):
            clave = "ANTHROPIC_API_KEY" if modelo.proveedor == "anthropic" else "GOOGLE_API_KEY"
            sin_correr[modelo.id] = f"falta {clave}"
            continue
        if presupuesto.agotado:
            sin_correr[modelo.id] = "no se corrió: se alcanzó el tope de gasto"
            continue
        print(f"Corriendo {modelo.id}…", file=sys.stderr)
        propios, cortado = await correr_modelo(
            modelo, casos, instrucciones, presupuesto, concurrencia=concurrencia
        )
        resultados += propios
        todas.append(metricas(modelo.id, len(casos), propios))
        if cortado:
            sin_correr[modelo.id] = "cortado por el tope de gasto"
    return todas, resultados, sin_correr


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)
    directorio = Path(args.dir)
    try:
        casos = cargar_casos(directorio / "casos.yaml")
    except (OSError, SetInvalidoError) as exc:
        print(f"El set de {directorio} no sirve:\n{exc}", file=sys.stderr)
        return 2
    instrucciones = (directorio / "instrucciones.md").read_text(encoding="utf-8").strip()
    cargar_credenciales(Path(args.var_local))
    elegidos, apagados = elegir_modelos(args.modelos, con_claude=args.con_claude)
    presupuesto = Presupuesto(args.tope_usd)
    todas, resultados, sin_correr = asyncio.run(
        _correr(elegidos, casos, instrucciones, presupuesto, args.concurrencia)
    )
    sin_correr = {**apagados, **sin_correr}
    fecha = datetime.now(UTC)
    (directorio / "RESULTADOS.md").write_text(
        informe_markdown(
            fecha=fecha,
            casos=casos,
            instrucciones=instrucciones,
            metricas_por_modelo=todas,
            resultados=resultados,
            sin_correr=sin_correr,
            gastado=presupuesto.gastado,
            tope=args.tope_usd,
        ),
        encoding="utf-8",
    )
    detalle = directorio / "resultados" / f"{fecha:%Y-%m-%dT%H%M%S}.json"
    detalle.parent.mkdir(parents=True, exist_ok=True)
    detalle.write_text(
        json.dumps(
            {
                "fecha": fecha.isoformat(),
                "gastado_usd": round(presupuesto.gastado, 6),
                "metricas": [asdict(m) for m in todas],
                "sin_correr": sin_correr,
                "resultados": [asdict(r) for r in resultados],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    for m in todas:
        print(
            f"{m.modelo}: recall alto {_pct(m.recall_alto)}, sospechosas como bajo "
            f"{m.estafas_como_bajo}, falsos positivos {_pct(m.falsos_positivos)}, "
            f"{_usd(m.costo_por_vacante)} por vacante"
        )
    for k, v in sin_correr.items():
        print(f"{k}: {v}")
    print(f"Gasto: {_usd(presupuesto.gastado, 4)}. Informe: {directorio / 'RESULTADOS.md'}")
    return 0 if todas else 2


if __name__ == "__main__":
    # La consola de Windows usa cp1252: sin esto, los acentos salen rotos.
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    raise SystemExit(main())
