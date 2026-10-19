"""El gancho del plan gratis: lo que la empresa sabe de sus CVs sin saber quién es quién.

ADR-017 §4 y ADR-018. Al estilo de "quién vio tu perfil": "Evaluamos 45 de tus
CVs en 38 segundos. 13 califican y 6 cumplen todas las skills". Los números
salen de las preevaluaciones guardadas, no de un prompt, y son los mismos que la
empresa verá candidato por candidato si contrata los servicios de IA.

Además del resumen, la empresa ve una evaluación de muestra, a ciegas y siempre
la misma (`elegir_muestra`). La base aplica estas reglas en `resumen_del_gancho()`
y `muestra_del_gancho()` (migración 0009), y las dos copias se prueban contra
`packages/types/contracts/gancho.json`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.siguiente_paso import UMBRAL_PSICOMETRICO

#: El resumen avanza de 5 en 5 CVs. Si cambiara con cada aplicación, comparar el
#: gancho antes y después de una diría si esa persona califica, que es justo lo
#: que se paga por ver.
TAMANO_DEL_LOTE = 5

#: Califica quien pasaría al psicométrico: el mismo umbral que usa el pipeline.
UMBRAL_CALIFICA = UMBRAL_PSICOMETRICO

#: La muestra se elige cuando hay dos lotes evaluados...
EVALUADAS_PARA_LA_MUESTRA = 10
#: ...y es la 6.ª por score de esas 10: enseña cómo se evalúa sin regalar a la
#: mejor candidata, que para una empresa con una sola vacante es todo el valor.
POSICION_DE_LA_MUESTRA = 6


@dataclass(frozen=True, slots=True)
class Preevaluacion:
    score: float
    #: Requisitos de la vacante que el CV no muestra (los `gaps` de cv-evaluator).
    gaps: tuple[str, ...]
    duracion_ms: int


@dataclass(frozen=True, slots=True)
class ResumenDelGancho:
    cvs_evaluados: int
    segundos: int
    califican: int
    cumplen_todas_las_skills: int


def califica(score: float) -> bool:
    return score >= UMBRAL_CALIFICA


def cumple_todas_las_skills(preevaluacion: Preevaluacion) -> bool:
    """Califica y no le falta ningún requisito. Es un subconjunto de los que califican."""
    return califica(preevaluacion.score) and not preevaluacion.gaps


def resumir(preevaluaciones: Sequence[Preevaluacion]) -> ResumenDelGancho:
    """Resume las preevaluaciones de una vacante, en el orden en que se hicieron.

    Solo cuentan los lotes completos; el resto espera al siguiente.
    """
    lote = preevaluaciones[: len(preevaluaciones) // TAMANO_DEL_LOTE * TAMANO_DEL_LOTE]
    return ResumenDelGancho(
        cvs_evaluados=len(lote),
        segundos=math.ceil(sum(p.duracion_ms for p in lote) / 1000),
        califican=sum(1 for p in lote if califica(p.score)),
        cumplen_todas_las_skills=sum(1 for p in lote if cumple_todas_las_skills(p)),
    )


def elegir_muestra(preevaluaciones: Sequence[Preevaluacion]) -> int | None:
    """Índice de la evaluación que se enseña como muestra, o None si aún no hay.

    Se elige entre las 10 primeras evaluadas y, una vez elegida, la base la deja
    fija: si cambiara con cada lote, la muestra destaparía candidatos uno a uno.
    Los empates se resuelven por orden de evaluación.
    """
    if len(preevaluaciones) < EVALUADAS_PARA_LA_MUESTRA:
        return None
    primeras = list(enumerate(preevaluaciones[:EVALUADAS_PARA_LA_MUESTRA]))
    por_score = sorted(primeras, key=lambda par: -par[1].score)
    return por_score[POSICION_DE_LA_MUESTRA - 1][0]
