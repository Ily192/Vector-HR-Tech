"""El esquema Pydantic de cv-evaluator cumple el mismo contrato que el de Zod.

El fichero compartido lo valida también `packages/types` con Vitest. Antes los dos
esquemas decían espejarse y no coincidían: `candidate_id` frente a `candidato_id`,
y `rationale` de 1 frente a 10 caracteres.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.clients.scoring import CvEvaluation

CONTRATO_PATH = Path(__file__).resolve().parents[4] / "packages/types/contracts/cv-evaluation.json"
CONTRATO: dict[str, Any] = json.loads(CONTRATO_PATH.read_text(encoding="utf-8"))


def test_tiene_exactamente_los_campos_del_contrato() -> None:
    assert sorted(CvEvaluation.model_fields) == sorted(CONTRATO["campos"])


@pytest.mark.parametrize("valido", CONTRATO["validos"])
def test_acepta_los_ejemplos_validos(valido: dict[str, Any]) -> None:
    CvEvaluation.model_validate(valido)


@pytest.mark.parametrize("caso", CONTRATO["invalidos"], ids=lambda c: c["motivo"])
def test_rechaza_los_ejemplos_invalidos(caso: dict[str, Any]) -> None:
    dato = {**CONTRATO["validos"][0], **caso.get("cambio", {})}
    dato.pop(caso.get("quitar", ""), None)
    with pytest.raises(ValidationError):
        CvEvaluation.model_validate(dato)
