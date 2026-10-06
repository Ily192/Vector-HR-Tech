"""Carga de los SKILL.md de producto: la única fuente de las instrucciones.

Hasta la sesión 7 ningún runtime leía los SKILL.md. El prompt que puntúa
candidatos estaba escrito a mano en `clients/scoring.py` y se había quedado sin
la calibración del score y sin la regla anti-sesgo que el SKILL.md declara. En
un producto que puntúa personas eso no es deuda técnica: es riesgo de
compliance.

Ahora el cuerpo del SKILL.md es lo que recibe el modelo, tal cual. Si falta o
está roto, se falla en el momento. Un fallback a un prompt escrito en código
sería volver a tener dos fuentes que divergen en silencio.

Dónde se buscan: `SKILLS_DIR` si está definido (la imagen Docker lo fija en
/app/skills), y si no el `.agents/skills` de la raíz del monorepo.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from app.config import settings

_DELIMITADOR = "---"


class SkillError(RuntimeError):
    """El SKILL.md no existe o no tiene el formato esperado."""


@dataclass(frozen=True, slots=True)
class Skill:
    name: str
    metadata: dict[str, Any]
    #: Cuerpo del SKILL.md sin el frontmatter: lo que se le manda al modelo.
    instructions: str


def skills_dir() -> Path:
    if settings.skills_dir:
        return Path(settings.skills_dir)
    aqui = Path(__file__).resolve()
    for padre in aqui.parents:
        candidato = padre / ".agents" / "skills"
        if candidato.is_dir():
            return candidato
    raise SkillError(
        f"No encuentro los SKILL.md: SKILLS_DIR no está definido y no hay un "
        f".agents/skills por encima de {aqui}",
    )


@cache
def load_skill(name: str) -> Skill:
    path = skills_dir() / name / "SKILL.md"
    try:
        # utf-8-sig: un BOM de un editor de Windows no puede romper el parseo.
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise SkillError(f"No existe el SKILL.md de '{name}': {path}") from exc

    metadata, instructions = _split_frontmatter(text, path)
    if metadata.get("name") != name:
        raise SkillError(
            f"{path}: el frontmatter dice name={metadata.get('name')!r}, "
            f"pero el directorio es {name!r}",
        )
    if not instructions:
        raise SkillError(f"{path}: el SKILL.md no tiene instrucciones")
    return Skill(name=name, metadata=metadata, instructions=instructions)


def _split_frontmatter(text: str, path: Path) -> tuple[dict[str, Any], str]:
    lineas = text.splitlines()
    if not lineas or lineas[0].strip() != _DELIMITADOR:
        raise SkillError(f"{path}: falta el frontmatter (la primera línea tiene que ser '---')")
    fin = next(
        (i for i, linea in enumerate(lineas[1:], start=1) if linea.strip() == _DELIMITADOR),
        None,
    )
    if fin is None:
        raise SkillError(f"{path}: el frontmatter no se cierra con '---'")
    try:
        metadata = yaml.safe_load("\n".join(lineas[1:fin])) or {}
    except yaml.YAMLError as exc:
        raise SkillError(f"{path}: el frontmatter no es YAML válido: {exc}") from exc
    if not isinstance(metadata, dict):
        raise SkillError(f"{path}: el frontmatter tiene que ser un mapa de clave: valor")
    return metadata, "\n".join(lineas[fin + 1 :]).strip()


def reset_cache() -> None:
    """Olvida los SKILL.md cargados (tests, o tras cambiar SKILLS_DIR)."""
    load_skill.cache_clear()
