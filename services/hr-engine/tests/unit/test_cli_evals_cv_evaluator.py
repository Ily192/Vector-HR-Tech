"""La CLI del arnés de cv-evaluator: el set de casos, el informe y las salidas (ADR-021 §9)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cli.evals_cv_evaluator import SET_SINTETICO, SetInvalidoError, cargar_set, main
from app.domain.anonimizacion import CvAnonimo, anonimizar
from app.domain.entidades import FitScore, ResultadoScoring
from app.domain.puertos import ProveedorNoDisponibleError

CASOS_YAML = """
umbrales:
  min_casos: 2
vacantes:
  analista:
    titulo: Analista de datos
    descripcion: Tableros en Power BI y consultas en SQL.
    skills: [SQL, Power BI]
casos:
  - id: fuerte
    cv: fuerte.txt
    nombre: Lucía Garza Treviño
    correo: lucia.garza@example.test
    vacante: analista
    esperado: 8.5
  - id: debil
    cv: debil.txt
    nombre: Jorge Ortiz Salinas
    correo: jorge.ortiz@example.test
    vacante: analista
    esperado: 2.0
"""

#: Un CV necesita 100 letras para leerse, como en producción (`es_legible`).
RELLENO = (
    "Trabajo con equipos de varias áreas, documento lo que hago y explico los resultados "
    "a quien no es técnico."
)
CVS = {
    "fuerte.txt": (
        "Lucía Garza Treviño\nlucia.garza@example.test\n"
        f"Cuatro años con SQL y Power BI en ventas. {RELLENO}"
    ),
    "debil.txt": (
        "Jorge Ortiz Salinas\njorge.ortiz@example.test\n"
        f"Soporte técnico de impresoras y redes. {RELLENO}"
    ),
}


class EvaluadorPorSkills:
    """Puntúa alto si el CV habla de SQL: lo justo para que el set fuerte/débil acierte."""

    def __init__(self) -> None:
        self.llamadas = 0

    async def evaluar(self, cv: CvAnonimo, vacante: str) -> ResultadoScoring:
        self.llamadas += 1
        return ResultadoScoring(
            fit=FitScore(score=8.0 if "SQL" in cv.texto else 2.5, rationale="Según sus skills."),
            cost_usd=0.0025,
            model="gemini-2.5-flash",
        )


class SinModelo:
    async def evaluar(self, cv: CvAnonimo, vacante: str) -> ResultadoScoring:
        raise ProveedorNoDisponibleError("sin GOOGLE_API_KEY")


def _set(tmp_path: Path, casos_yaml: str = CASOS_YAML, cvs: dict[str, str] = CVS) -> Path:
    (tmp_path / "casos.yaml").write_text(casos_yaml, encoding="utf-8")
    for nombre, texto in cvs.items():
        (tmp_path / nombre).write_text(texto, encoding="utf-8")
    return tmp_path


# ─────────────────────────────── el set sintético ───────────────────────────────


def test_el_set_sintetico_del_repo_carga_entero() -> None:
    set_de_casos = cargar_set(SET_SINTETICO)

    assert len(set_de_casos.casos) == 8
    assert all(c.esperado is not None for c in set_de_casos.casos)
    assert set_de_casos.umbrales.min_casos == 8
    assert {c.vacante.titulo for c in set_de_casos.casos} == {
        "Analista de datos",
        "Coordinador de almacén",
    }


def test_en_el_set_sintetico_el_anonimizador_quita_a_cada_persona() -> None:
    for caso in cargar_set(SET_SINTETICO).casos:
        cv = anonimizar(caso.texto, nombre=caso.nombre, correo=caso.correo)
        assert caso.nombre is not None and caso.correo is not None
        assert caso.correo not in cv.texto, caso.id
        assert caso.nombre.split()[0] not in cv.texto, caso.id


# ──────────────────────────────── cargar un set ────────────────────────────────


def test_un_set_con_problemas_los_dice_todos_juntos(tmp_path: Path) -> None:
    casos_yaml = CASOS_YAML.replace("cv: debil.txt", "cv: no-esta.txt").replace(
        "esperado: 8.5", "esperado: 12"
    ) + (
        "  - id: fuerte\n    cv: fuerte.txt\n    vacante: analista\n"
        "  - id: otra\n    cv: fuerte.txt\n    vacante: gerente\n"
    )
    with pytest.raises(SetInvalidoError) as exc:
        cargar_set(_set(tmp_path, casos_yaml))

    problemas = str(exc.value)
    assert "fuerte: esperado tiene que ir de 0 a 10" in problemas
    assert "debil: no está el cv no-esta.txt" in problemas
    assert "fuerte: el id está repetido" in problemas
    assert "otra: no existe la vacante 'gerente'" in problemas


def test_un_cv_fuera_del_directorio_no_se_lee(tmp_path: Path) -> None:
    afuera = tmp_path / "afuera.txt"
    afuera.write_text("SQL y Power BI desde 2020, con tableros para ventas.", encoding="utf-8")
    directorio = tmp_path / "set"
    directorio.mkdir()
    with pytest.raises(SetInvalidoError, match=r"no está el cv \.\./afuera\.txt"):
        cargar_set(_set(directorio, CASOS_YAML.replace("cv: fuerte.txt", "cv: ../afuera.txt")))


def test_sin_casos_yaml_no_hay_set(tmp_path: Path) -> None:
    with pytest.raises(SetInvalidoError, match=r"no hay casos.yaml"):
        cargar_set(tmp_path)


# ─────────────────────────────── correr la CLI ───────────────────────────────


def test_mide_escribe_el_informe_sin_nombres_y_sale_con_0_si_pasa(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directorio = _set(tmp_path)
    evaluador = EvaluadorPorSkills()

    codigo = main(["--dir", str(directorio), "--repeticiones", "2"], evaluador=evaluador)

    assert codigo == 0
    # 2 casos x 2 repeticiones, más 2 casos x 3 ejes x 2 valores x 2 repeticiones.
    assert evaluador.llamadas == 4 + 24
    (archivo,) = (directorio / "resultados").glob("*.json")
    texto = archivo.read_text(encoding="utf-8")
    informe = json.loads(texto)
    assert informe["pasa"] is True
    assert informe["skill"]["nombre"] == "cv-evaluator"
    assert [c["id"] for c in informe["acierto"]["casos"]] == ["fuerte", "debil"]
    assert informe["sesgo"]["sesgados"] == 0
    for dato in ("Lucía", "Garza", "lucia.garza@example.test", "Jorge"):
        assert dato not in texto
    salida = capsys.readouterr().out
    assert "PASA" in salida
    assert "Pearson r 1.00" in salida


def test_sale_con_1_si_no_pasa_y_dice_por_que(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    casos_yaml = CASOS_YAML.replace("esperado: 2.0", "esperado: 9.5").replace(
        "min_casos: 2", "min_casos: 5"
    )
    salida = tmp_path / "informe.json"
    codigo = main(
        ["--dir", str(_set(tmp_path, casos_yaml)), "--sin-sesgo", "--salida", str(salida)],
        evaluador=EvaluadorPorSkills(),
    )

    assert codigo == 1
    assert json.loads(salida.read_text(encoding="utf-8"))["fallas"][0] == (
        "2 casos con score esperado; hacen falta 5"
    )
    assert "NO PASA" in capsys.readouterr().out


def test_sin_modelo_sale_con_2_y_no_escribe_informe(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directorio = _set(tmp_path)

    assert main(["--dir", str(directorio)], evaluador=SinModelo()) == 2
    assert not (directorio / "resultados").exists()
    assert "GOOGLE_API_KEY" in capsys.readouterr().err


def test_un_set_invalido_sale_con_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--dir", str(tmp_path)], evaluador=EvaluadorPorSkills()) == 2
    assert "no sirve para medir" in capsys.readouterr().err
