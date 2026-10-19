"""La regla del gancho del plan gratis (ADR-019) y su contrato.

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
    ResumenDelGancho,
    menciona_la_mayoria,
    menciona_todas,
    resumir,
)

CONTRATOS = Path(__file__).resolve().parents[4] / "packages/types/contracts"
CONTRATO: dict[str, Any] = json.loads((CONTRATOS / "gancho.json").read_text(encoding="utf-8"))


def test_el_lote_es_el_del_contrato() -> None:
    assert CONTRATO["tamano_del_lote"] == TAMANO_DEL_LOTE


@pytest.mark.parametrize("caso", CONTRATO["casos"], ids=lambda c: c["nombre"])
def test_casos_del_contrato(caso: dict[str, Any]) -> None:
    encontradas = [len(e) for e in caso["encontradas"]]
    assert resumir(encontradas, len(caso["skills"])) == ResumenDelGancho(**caso["resumen"])


def test_la_mayoria_es_mas_de_la_mitad() -> None:
    assert menciona_la_mayoria(3, 4)
    assert not menciona_la_mayoria(2, 4)
    assert menciona_la_mayoria(2, 3)
    assert not menciona_la_mayoria(1, 2)


def test_mencionar_todas_tambien_es_mencionar_la_mayoria() -> None:
    for skills in range(1, 16):
        assert menciona_todas(skills, skills)
        assert menciona_la_mayoria(skills, skills)


def test_sin_skills_no_hay_nada_que_contar() -> None:
    assert not menciona_todas(0, 0)
    assert not menciona_la_mayoria(0, 0)
    assert resumir([0] * 10, 0) == ResumenDelGancho(revisados=0, con_la_mayoria=0, con_todas=0)


def test_el_resumen_no_cambia_hasta_completar_el_lote() -> None:
    """Un CV solo no mueve los números: no se puede deducir qué menciona esa persona."""
    base = [1] * TAMANO_DEL_LOTE
    antes = resumir(base, 3)
    for extra in range(1, TAMANO_DEL_LOTE):
        assert resumir(base + [3] * extra, 3) == antes
