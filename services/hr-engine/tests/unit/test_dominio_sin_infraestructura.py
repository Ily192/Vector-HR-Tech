"""El dominio solo depende de la biblioteca estándar y de sí mismo.

Es una lista de permitidos, no de prohibidos: cualquier dependencia nueva
(pydantic, SQLAlchemy, un SDK, otro módulo de `app`) rompe el test sin que haga
falta acordarse de añadirla a una lista negra.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

DOMINIO = Path(__file__).resolve().parents[2] / "app" / "domain"
MODULOS = sorted(DOMINIO.rglob("*.py"))


def _permitido(modulo: str) -> bool:
    raiz = modulo.split(".")[0]
    return (
        raiz in sys.stdlib_module_names
        or modulo == "app.domain"
        or modulo.startswith("app.domain.")
    )


def _imports_no_permitidos(codigo: str) -> list[str]:
    """Los imports absolutos que no son stdlib ni dominio. Cuentan también los de
    `if TYPE_CHECKING:`; los relativos no salen del paquete."""
    malos: list[str] = []
    for nodo in ast.walk(ast.parse(codigo)):
        if isinstance(nodo, ast.Import):
            nombres = [alias.name for alias in nodo.names]
        elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and nodo.module:
            nombres = [nodo.module]
        else:
            continue
        malos.extend(n for n in nombres if not _permitido(n))
    return malos


def test_hay_modulos_que_comprobar() -> None:
    # Si la carpeta se mueve, el test parametrizado pasaría sin comprobar nada.
    nombres = {p.name for p in MODULOS}
    assert {"entidades.py", "puertos.py", "presupuesto.py", "siguiente_paso.py"} <= nombres


@pytest.mark.parametrize("modulo", MODULOS, ids=lambda p: p.name)
def test_el_dominio_solo_importa_stdlib_y_dominio(modulo: Path) -> None:
    assert _imports_no_permitidos(modulo.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    "codigo",
    [
        "import sqlalchemy",
        "from sqlalchemy.ext.asyncio import AsyncSession",
        "from celery import Task",
        "from pydantic import BaseModel",
        "from openai import AsyncOpenAI",
        "from app.clients.scoring import score_candidate_fit",
        "from app.workers import run_state",
        "import app.database",
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from sqlalchemy import text",
    ],
)
def test_la_guarda_detecta_imports_de_fuera(codigo: str) -> None:
    assert _imports_no_permitidos(codigo) != []


def test_la_guarda_deja_pasar_stdlib_y_dominio() -> None:
    codigo = (
        "from __future__ import annotations\n"
        "import dataclasses\n"
        "from typing import Protocol\n"
        "from uuid import UUID\n"
        "from app.domain.entidades import FitScore\n"
        "from . import siguiente_paso\n"
    )
    assert _imports_no_permitidos(codigo) == []
