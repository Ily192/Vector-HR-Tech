"""El prompt que puntúa personas sale del SKILL.md, y lleva sus reglas.

Tarjeta F0·3. Antes el system instruction era un texto escrito a mano en
clients/scoring.py, sin la calibración del score ni la regla anti-sesgo que el
SKILL.md declaraba. Ningún runtime leía el SKILL.md.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from app import skills
from app.clients import scoring
from app.config import Settings, settings

#: Frases que TIENEN que llegarle al modelo. Si alguien las quita del SKILL.md,
#: o el SKILL.md deja de cargarse, este test falla: quitarlas tiene que ser una
#: decisión explícita, con este test cambiado en el mismo PR.
_REGLAS_OBLIGATORIAS = {
    "anti-sesgo": "ignorá edad, género, nacionalidad",
    "no inventar": "No inventes experiencia que no está en el CV",
    "calibración 0-3": "0-3: claramente no aplica",
    "calibración 4-6": "4-6: aplica parcial",
    "calibración 7-8": "7-8: buen fit",
    "calibración 9-10": "9-10: excelente fit",
}

_RESPUESTA_VALIDA = (
    '{"score": 7.5, "rationale": "Buen match con el ICP", "gaps": [], '
    '"strengths": ["python"], "recommended_next_step": "entrevista"}'
)


@pytest.fixture(autouse=True)
def _sin_cache() -> Iterator[None]:
    skills.reset_cache()
    yield
    skills.reset_cache()


class _Uso:
    prompt_token_count = 120
    candidates_token_count = 40


class _Respuesta:
    text = _RESPUESTA_VALIDA
    usage_metadata = _Uso()


class _ModelosQueGraban:
    def __init__(self) -> None:
        self.llamadas: list[dict[str, Any]] = []

    async def generate_content(self, *, model: str, contents: str, config: Any) -> _Respuesta:
        self.llamadas.append({"model": model, "contents": contents, "config": config})
        return _Respuesta()


class _ClienteFalso:
    def __init__(self, modelos: _ModelosQueGraban) -> None:
        self.aio = type("Aio", (), {"models": modelos})()


async def _lo_que_recibe_el_modelo(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    modelos = _ModelosQueGraban()
    monkeypatch.setattr(scoring, "_get_client", lambda: _ClienteFalso(modelos))
    await scoring.score_candidate_fit(
        {"full_name": "Ana Dev", "headline": "Senior Python", "summary": "10 años con Python"},
        "ICP: backend Python",
    )
    return modelos.llamadas[0]


@pytest.mark.asyncio
async def test_el_modelo_recibe_la_calibracion_y_la_regla_anti_sesgo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llamada = await _lo_que_recibe_el_modelo(monkeypatch)
    instruccion = str(llamada["config"].system_instruction)
    faltan = [regla for regla, frase in _REGLAS_OBLIGATORIAS.items() if frase not in instruccion]
    assert not faltan, f"Al modelo no le llegan estas reglas: {faltan}"


@pytest.mark.asyncio
async def test_el_system_instruction_es_el_skill_md_tal_cual(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Una sola fuente: lo que recibe el modelo es el cuerpo del SKILL.md."""
    llamada = await _lo_que_recibe_el_modelo(monkeypatch)
    assert llamada["config"].system_instruction == skills.load_skill("cv-evaluator").instructions


@pytest.mark.parametrize("nombre", ["cv-evaluator", "sourcer"])
def test_el_skill_declara_el_modelo_que_usa_el_codigo(nombre: str) -> None:
    modelos = skills.load_skill(nombre).metadata["models"]
    assert modelos["default"] == Settings.model_fields["default_scoring_model"].default
    # El código no tiene fallback: declarar uno es prometer algo que no existe.
    assert "fallback" not in modelos


# ─── Un SKILL.md roto falla fuerte, no manda basura al modelo ───────────────


@pytest.fixture
def skills_en_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "skills_dir", str(tmp_path))
    return tmp_path


def test_si_no_existe_dice_donde_lo_busco(skills_en_tmp: Path) -> None:
    with pytest.raises(
        skills.SkillError, match=re.escape("No existe el SKILL.md de 'cv-evaluator'")
    ):
        skills.load_skill("cv-evaluator")


@pytest.mark.parametrize(
    ("contenido", "error"),
    [
        ("Sos un evaluador.", "falta el frontmatter"),
        ("---\nname: cv-evaluator\nSos un evaluador.", "no se cierra"),
        ("---\nname: [cv-evaluator\n---\nSos un evaluador.", "no es YAML válido"),
        ("---\nname: otro\n---\nSos un evaluador.", "el frontmatter dice name='otro'"),
        ("---\nname: cv-evaluator\n---\n\n", "no tiene instrucciones"),
    ],
)
def test_un_skill_mal_formado_falla(skills_en_tmp: Path, contenido: str, error: str) -> None:
    directorio = skills_en_tmp / "cv-evaluator"
    directorio.mkdir()
    (directorio / "SKILL.md").write_text(contenido, encoding="utf-8")
    with pytest.raises(skills.SkillError, match=error):
        skills.load_skill("cv-evaluator")
