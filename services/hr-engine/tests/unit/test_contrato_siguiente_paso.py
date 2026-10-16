"""La política del siguiente paso cumple el contrato que espeja `packages/types`.

El mismo fichero lo valida `packages/types/src/__tests__/reglas.test.ts`, para que
la UI no anuncie un paso distinto del que asigna el backend.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.domain.siguiente_paso import UMBRAL_ENTREVISTA, UMBRAL_PSICOMETRICO, siguiente_paso

CONTRATO_PATH = Path(__file__).resolve().parents[4] / "packages/types/contracts/siguiente-paso.json"
CONTRATO: dict[str, Any] = json.loads(CONTRATO_PATH.read_text(encoding="utf-8"))


def test_umbrales_del_contrato() -> None:
    assert CONTRATO["umbrales"] == {
        "psicometrico": UMBRAL_PSICOMETRICO,
        "entrevista": UMBRAL_ENTREVISTA,
    }


@pytest.mark.parametrize("caso", CONTRATO["casos"], ids=lambda c: str(c["score"]))
def test_casos_del_contrato(caso: dict[str, Any]) -> None:
    assert siguiente_paso(caso["score"]) == caso["paso"]
