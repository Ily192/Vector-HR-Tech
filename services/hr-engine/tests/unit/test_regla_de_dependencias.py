"""Regla de dependencias: el núcleo solo depende de la biblioteca estándar y de sí mismo.

Las dependencias apuntan hacia adentro. La aplicación puede importar el dominio;
el dominio no importa la aplicación, y ninguno de los dos importa infraestructura.

Es una lista de permitidos, no de prohibidos: cualquier dependencia nueva
(pydantic, SQLAlchemy, un SDK, otro módulo de `app`) rompe el test sin que haga
falta acordarse de añadirla a una lista negra.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"

#: Lo que puede importar cada capa, además de la biblioteca estándar.
CAPAS: dict[str, tuple[str, ...]] = {
    "domain": ("app.domain",),
    "application": ("app.domain", "app.application"),
}
MODULOS = [(capa, ruta) for capa in CAPAS for ruta in sorted((APP / capa).rglob("*.py"))]


def _permitido(modulo: str, capas: tuple[str, ...]) -> bool:
    return modulo.split(".")[0] in sys.stdlib_module_names or any(
        modulo == capa or modulo.startswith(f"{capa}.") for capa in capas
    )


def _imports_no_permitidos(codigo: str, capas: tuple[str, ...]) -> list[str]:
    """Los imports absolutos que no son stdlib ni de `capas`. Cuentan también los de
    `if TYPE_CHECKING:`; los relativos no salen del paquete."""
    malos: list[str] = []
    for nodo in ast.walk(ast.parse(codigo)):
        if isinstance(nodo, ast.Import):
            nombres = [alias.name for alias in nodo.names]
        elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and nodo.module:
            nombres = [nodo.module]
        else:
            continue
        malos.extend(n for n in nombres if not _permitido(n, capas))
    return malos


def test_hay_modulos_que_comprobar() -> None:
    # Si una carpeta se mueve, el test parametrizado pasaría sin comprobar nada.
    presentes = {(capa, ruta.name) for capa, ruta in MODULOS}
    assert {
        ("domain", "entidades.py"),
        ("domain", "puertos.py"),
        ("domain", "presupuesto.py"),
        ("domain", "siguiente_paso.py"),
        ("domain", "plan.py"),
        ("domain", "gancho.py"),
        ("domain", "coincidencia.py"),
        ("application", "evaluate_candidate.py"),
    } <= presentes


@pytest.mark.parametrize(
    ("capa", "modulo"), MODULOS, ids=[f"{capa}/{ruta.name}" for capa, ruta in MODULOS]
)
def test_cada_capa_solo_importa_stdlib_y_lo_permitido(capa: str, modulo: Path) -> None:
    assert _imports_no_permitidos(modulo.read_text(encoding="utf-8"), CAPAS[capa]) == []


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
        # El dominio tampoco mira hacia la aplicación.
        "from app.application.evaluate_candidate import EvaluateCandidate",
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from sqlalchemy import text",
    ],
)
def test_la_guarda_detecta_imports_de_fuera_en_el_dominio(codigo: str) -> None:
    assert _imports_no_permitidos(codigo, CAPAS["domain"]) != []


@pytest.mark.parametrize(
    "codigo",
    [
        "from app.clients.embeddings import embed_text",
        "from app.repositories import hr",
        "from app.workers.cv_evaluator import _run",
        "from app.monitoring import logger",
        "from sqlalchemy import text",
    ],
)
def test_la_guarda_detecta_infraestructura_en_la_aplicacion(codigo: str) -> None:
    assert _imports_no_permitidos(codigo, CAPAS["application"]) != []


def test_la_guarda_deja_pasar_stdlib_y_lo_permitido() -> None:
    dominio = (
        "from __future__ import annotations\n"
        "import dataclasses\n"
        "from typing import Protocol\n"
        "from uuid import UUID\n"
        "from app.domain.entidades import FitScore\n"
        "from . import siguiente_paso\n"
    )
    aplicacion = (
        "from app.domain.puertos import ScoringProvider\n"
        "from app.application import evaluate_candidate\n"
    )
    assert _imports_no_permitidos(dominio, CAPAS["domain"]) == []
    assert _imports_no_permitidos(aplicacion, CAPAS["application"]) == []
