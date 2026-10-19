"""Los límites del plan cumplen el contrato que espejan `packages/types` y la migración 0008.

El mismo fichero lo validan `packages/types/src/__tests__/reglas.test.ts` (UI) y
`tests/security/test_plan_gratis.py` (la copia en SQL).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.domain.plan import MAX_APLICACIONES_GRATIS, limite_de_vacantes, limites_del_plan

CONTRATO_PATH = Path(__file__).resolve().parents[4] / "packages/types/contracts/limites-plan.json"
CONTRATO: dict[str, Any] = json.loads(CONTRATO_PATH.read_text(encoding="utf-8"))


def test_maximo_de_aplicaciones() -> None:
    assert CONTRATO["max_aplicaciones_gratis"] == MAX_APLICACIONES_GRATIS


@pytest.mark.parametrize("plan", ["gratis", "ia"])
def test_modulos_etapas_y_topes_de_cada_plan(plan: str) -> None:
    esperado = CONTRATO["planes"][plan]
    limites = limites_del_plan(plan)  # type: ignore[arg-type]
    assert list(limites.modulos) == esperado["modulos"]
    assert list(limites.etapas_visibles) == esperado["etapas_visibles"]
    assert (limites.vacantes_activas is not None) == esperado["con_limites"]


@pytest.mark.parametrize(
    "caso", CONTRATO["casos_limite_de_vacantes"], ids=lambda c: f"{c['tamano']}-{c['ajuste']}"
)
def test_casos_del_limite_de_vacantes(caso: dict[str, Any]) -> None:
    assert limite_de_vacantes(caso["tamano"], caso["ajuste"]) == caso["limite"]
