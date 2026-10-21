"""El aviso de los diagnósticos gratuitos de vectorhrtech.com (migración 0017).

Un prospecto responde el diagnóstico y deja nombre, empresa, correo y el origen de
la campaña. Vector HR se entera por un correo de resumen a `AVISO_DIAGNOSTICOS_PARA`:

- Uno por barrido, con todos los diagnósticos nuevos que pasaron Turnstile. Resend
  cobra por correo y la cuota del plan gratis (100 al día) es la misma de Auth.
- Hasta `max_por_dia` diagnósticos con detalle al día; los que pasan del tope van
  en una línea y quedan en la base.
- Todo lo que escribió el prospecto es texto no confiable: va solo en el cuerpo, en
  texto plano y sin caracteres de control. El asunto lo arma esta capa, en una línea.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

#: Diagnósticos por barrido. Con el freno de la base (300 en 24 h) sobra.
LOTE_DE_AVISOS = 20
#: Correos fallidos antes de dejar de intentarlo; el diagnóstico sigue en la base.
MAX_INTENTOS_AVISO = 5
#: Procesos del detalle de cada diagnóstico.
PROCESOS_EN_EL_AVISO = 3
#: Largo máximo de cada dato del prospecto en el correo y de la empresa en el asunto.
MAX_LARGO_EN_EL_CUERPO = 160
MAX_LARGO_EN_EL_ASUNTO = 60

_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]+")


@dataclass(frozen=True, slots=True)
class Diagnostico:
    id: UUID
    creado_en: datetime
    nombre: str
    empresa: str
    correo: str
    origen: str | None
    utm_medium: str | None
    utm_campaign: str | None
    horas_recuperables_mes: float
    #: Como lo guardó el navegador: no confiable.
    resultado: dict[str, Any]
    ip: str | None
    turnstile_token: str | None
    #: Ya pasó Turnstile en un barrido anterior.
    verificado: bool


@dataclass(frozen=True, slots=True)
class ProcesoDelAviso:
    nombre: str
    etapa: str
    horas_recuperables_mes: float


@dataclass(frozen=True, slots=True)
class CorreoSaliente:
    para: str
    asunto: str
    cuerpo: str


def una_linea(texto: object, largo: int = MAX_LARGO_EN_EL_CUERPO) -> str:
    """El texto en una sola línea, sin caracteres de control y recortado a `largo`."""
    limpio = " ".join(_CONTROL.sub(" ", str(texto)).split())
    return limpio if len(limpio) <= largo else limpio[: largo - 1].rstrip() + "…"


def _numero(valor: object) -> float | None:
    if isinstance(valor, bool) or not isinstance(valor, int | float):
        return None
    return float(valor) if math.isfinite(valor) else None


def top_procesos(resultado: dict[str, Any]) -> list[ProcesoDelAviso]:
    """Los primeros procesos del `resultado`, que el navegador guarda de mayor a menor.

    Lo que no tenga la forma esperada se salta: un resultado roto no tumba el aviso.
    """
    procesos = resultado.get("procesos")
    if not isinstance(procesos, list):
        return []
    top: list[ProcesoDelAviso] = []
    for proceso in procesos:
        if not isinstance(proceso, dict):
            continue
        horas = _numero(proceso.get("horasRecuperablesMes"))
        nombre = proceso.get("nombre")
        if horas is None or not isinstance(nombre, str) or not nombre.strip():
            continue
        top.append(
            ProcesoDelAviso(
                nombre=una_linea(nombre, 80),
                etapa=una_linea(proceso.get("etapa") or "", 20),
                horas_recuperables_mes=horas,
            )
        )
        if len(top) == PROCESOS_EN_EL_AVISO:
            break
    return top


def _horas(valor: float) -> str:
    return f"{valor:,.1f}".replace(",", " ")


def _detalle(diagnostico: Diagnostico) -> list[str]:
    origen = " / ".join(
        una_linea(v, 120)
        for v in (diagnostico.origen, diagnostico.utm_medium, diagnostico.utm_campaign)
        if v
    )
    lineas = [
        f"Empresa: {una_linea(diagnostico.empresa)}",
        f"Nombre: {una_linea(diagnostico.nombre)}",
        f"Correo: {una_linea(diagnostico.correo, 254)}",
        f"Origen: {origen or 'directo (sin utm)'}",
        f"Horas recuperables al mes: {_horas(diagnostico.horas_recuperables_mes)}",
    ]
    anio = _numero(diagnostico.resultado.get("horasRecuperablesAnio"))
    if anio is not None:
        lineas.append(f"Horas recuperables al año: {_horas(anio)}")
    procesos = top_procesos(diagnostico.resultado)
    if procesos:
        lineas.append("Procesos que más tiempo le quitan:")
        lineas += [
            f"  {i}. {p.nombre} ({p.etapa}): {_horas(p.horas_recuperables_mes)} h al mes"
            if p.etapa
            else f"  {i}. {p.nombre}: {_horas(p.horas_recuperables_mes)} h al mes"
            for i, p in enumerate(procesos, start=1)
        ]
    lineas.append(f"Fecha: {diagnostico.creado_en.strftime('%Y-%m-%d %H:%M %Z').strip()}")
    lineas.append(f"Id: {diagnostico.id}")
    return lineas


def resumen(
    para: str, detallados: Sequence[Diagnostico], sin_detalle: int
) -> CorreoSaliente | None:
    """El correo del barrido, o None si no hay nada que avisar."""
    total = len(detallados) + sin_detalle
    if total == 0:
        return None
    if len(detallados) == 1 and sin_detalle == 0:
        asunto = f"Nuevo diagnóstico: {una_linea(detallados[0].empresa, MAX_LARGO_EN_EL_ASUNTO)}"
    else:
        asunto = f"Nuevos diagnósticos: {total}"

    lineas = [
        "Diagnóstico gratuito de vectorhrtech.com.",
        "Lo de abajo lo escribió el prospecto: no abras enlaces que traiga.",
    ]
    for diagnostico in detallados:
        lineas += ["", "─" * 40, *_detalle(diagnostico)]
    if sin_detalle:
        lineas += [
            "",
            f"y {sin_detalle} diagnóstico{'s' if sin_detalle != 1 else ''} más "
            "(revísalos en la base)",
        ]
    return CorreoSaliente(para=para, asunto=una_linea(asunto, 120), cuerpo="\n".join(lineas) + "\n")
