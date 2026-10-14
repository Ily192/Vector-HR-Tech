"""Política determinista del siguiente paso de un candidato según su score.

El modelo aporta el score y el razonamiento; qué se hace después con la persona
lo decide esta regla. Antes lo elegía el LLM y nada comprobaba que cuadrara con
el score: un 8.5 con "rechazar" se aceptaba.

Los tramos son los del SKILL.md de cv-evaluator, sin huecos entre ellos: un 6.5
(que el SKILL.md no cubría) cae en psicométrico.
"""

from __future__ import annotations

from typing import Literal

SiguientePaso = Literal["rechazar", "psicometrico", "entrevista"]

#: Por debajo de este score se rechaza.
UMBRAL_PSICOMETRICO = 4.0
#: Desde este score se pasa directo a entrevista.
UMBRAL_ENTREVISTA = 7.0


def siguiente_paso(score: float) -> SiguientePaso:
    """< 4 rechazar · [4, 7) psicométrico · ≥ 7 entrevista."""
    if score < UMBRAL_PSICOMETRICO:
        return "rechazar"
    if score < UMBRAL_ENTREVISTA:
        return "psicometrico"
    return "entrevista"
