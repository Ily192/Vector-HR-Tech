"""La regla del gancho del plan gratis (ADR-018) y su contrato.

El mismo `contracts/gancho.json` lo valida `tests/security/test_gancho.py` contra
la copia en SQL (`resumen_del_gancho()`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.domain.gancho import (
    TAMANO_DEL_LOTE,
    UMBRAL_CALIFICA,
    Preevaluacion,
    ResumenDelGancho,
    califica,
    cumple_todas_las_skills,
    resumir,
)

CONTRATOS = Path(__file__).resolve().parents[4] / "packages/types/contracts"
CONTRATO: dict[str, Any] = json.loads((CONTRATOS / "gancho.json").read_text(encoding="utf-8"))
SIGUIENTE_PASO: dict[str, Any] = json.loads(
    (CONTRATOS / "siguiente-paso.json").read_text(encoding="utf-8")
)


def _preevaluaciones(caso: dict[str, Any]) -> list[Preevaluacion]:
    return [
        Preevaluacion(score=e["score"], gaps=tuple(e["gaps"]), duracion_ms=e["ms"])
        for e in caso["evaluaciones"]
    ]


def test_el_lote_es_el_del_contrato() -> None:
    assert CONTRATO["tamano_del_lote"] == TAMANO_DEL_LOTE


def test_califica_quien_pasaria_al_psicometrico() -> None:
    assert SIGUIENTE_PASO["umbrales"]["psicometrico"] == UMBRAL_CALIFICA
    assert califica(UMBRAL_CALIFICA)
    assert not califica(UMBRAL_CALIFICA - 0.1)


def test_cumplir_todas_las_skills_exige_calificar() -> None:
    assert cumple_todas_las_skills(Preevaluacion(score=8, gaps=(), duracion_ms=1))
    assert not cumple_todas_las_skills(Preevaluacion(score=8, gaps=("SQL",), duracion_ms=1))
    # Sin gaps pero por debajo del umbral: no se cuenta como "todas las skills".
    assert not cumple_todas_las_skills(Preevaluacion(score=3.9, gaps=(), duracion_ms=1))


@pytest.mark.parametrize("caso", CONTRATO["casos"], ids=lambda c: c["nombre"])
def test_casos_del_contrato(caso: dict[str, Any]) -> None:
    assert resumir(_preevaluaciones(caso)) == ResumenDelGancho(**caso["resumen"])


def test_el_resumen_no_cambia_hasta_completar_el_lote() -> None:
    """Una aplicación sola no mueve los números: no se puede deducir si esa persona califica."""
    base = [Preevaluacion(score=5, gaps=(), duracion_ms=1000)] * TAMANO_DEL_LOTE
    antes = resumir(base)
    for extra in range(1, TAMANO_DEL_LOTE):
        assert resumir(base + [Preevaluacion(score=9, gaps=(), duracion_ms=1)] * extra) == antes


def test_los_segundos_se_redondean_hacia_arriba() -> None:
    lote = [Preevaluacion(score=1, gaps=(), duracion_ms=201)] * TAMANO_DEL_LOTE
    assert resumir(lote).segundos == 2  # 1005 ms
