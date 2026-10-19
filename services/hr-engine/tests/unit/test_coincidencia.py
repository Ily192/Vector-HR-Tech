"""La coincidencia de skills sin IA que alimenta el gancho del plan gratis (ADR-019).

Una skill cuenta si el CV la menciona como frase completa. Estos tests fijan lo
que eso significa con los casos que más confunden a un Ctrl+F.
"""

from __future__ import annotations

import pytest

from app.domain.coincidencia import (
    MAX_SKILLS,
    MIN_LETRAS_LEGIBLES,
    SINONIMOS,
    Coincidencia,
    coincidir,
    es_legible,
    normalizar,
    skills_validas,
)

CV = """
María López · Ciudad de México · maria@example.test
Analista de datos con 4 años de experiencia. Python, SQL y Power BI.
Experiencia con NodeJS y React.js en proyectos de e-commerce.
Idiomas: English (C1), portugués básico.
Licencias de conducir tipo B. Manejo de almacenes y atención al cliente.
Herramientas: Excel avanzado, SAP S/4HANA, CI/CD con GitHub Actions, C++ y C#.
"""


def _encontradas(*skills: str, cv: str = CV) -> tuple[str, ...]:
    return coincidir(cv, skills).encontradas


def test_separa_encontradas_y_faltantes_en_el_orden_de_la_vacante() -> None:
    assert coincidir(CV, ["SQL", "Docker", "Python", "Kotlin"]) == Coincidencia(
        encontradas=("SQL", "Python"), faltantes=("Docker", "Kotlin")
    )


def test_conserva_como_escribio_la_skill_la_empresa() -> None:
    assert _encontradas("  python ", "POWER BI") == ("  python ", "POWER BI")


def test_ignora_mayusculas_y_acentos() -> None:
    assert _encontradas("ANALISTA DE DATOS", "Portugués", "excel avanzado") == (
        "ANALISTA DE DATOS",
        "Portugués",
        "excel avanzado",
    )


def test_una_skill_no_aparece_dentro_de_otra_palabra() -> None:
    cv = "Desarrollador JavaScript y TypeScript. PostgreSQL. Scala."
    assert _encontradas("Java", "Script", "SQL", "Scala", cv=cv) == ("Scala",)


def test_c_mas_mas_y_c_sharp_no_son_c() -> None:
    assert _encontradas("C++", "C#", cv=CV) == ("C++", "C#")
    assert _encontradas("C", cv="Programo en C++ y C#.") == ()
    assert _encontradas("C", cv="Programo en C y en Rust.") == ("C",)


def test_las_skills_cortas_respetan_mayusculas() -> None:
    """ "go", "r" o "qa" en minúsculas son palabras comunes: solo cuentan como se escribió la skill."""
    cv = "Backend en Go. Pruebas de QA. Ready to go-live."
    assert _encontradas("Go", "QA", cv=cv) == ("Go", "QA")
    assert _encontradas("R", cv="Estadística con R y Python.") == ("R",)
    assert _encontradas("R", cv="Responsable de ventas.") == ()


def test_admite_el_plural_pero_no_al_reves() -> None:
    assert _encontradas("Licencia de conducir", "Almacén", "Cliente") == (
        "Licencia de conducir",
        "Almacén",
        "Cliente",
    )
    # Quitar letras daría falsos positivos ("sales" → "sal").
    assert _encontradas("Licencias de manejo", cv="Licencia de manejo vigente.") == ()


def test_variantes_de_escritura_y_traducciones() -> None:
    assert _encontradas("Node.js", "React", "Inglés", "E-commerce") == (
        "Node.js",
        "React",
        "Inglés",
        "E-commerce",
    )


def test_los_sinonimos_no_incluyen_lo_que_una_skill_implica() -> None:
    """Quien sabe PostgreSQL sabe SQL, pero si el CV no dice SQL, no lo menciona."""
    assert _encontradas("SQL", cv="Base de datos PostgreSQL y MySQL.") == ()
    for grupo in SINONIMOS:
        assert "sql" not in grupo


def test_la_puntuacion_no_rompe_las_frases() -> None:
    assert _encontradas("CI/CD", "SAP S/4HANA", "Atención al cliente") == (
        "CI/CD",
        "SAP S/4HANA",
        "Atención al cliente",
    )
    assert _encontradas("Python", cv="Lenguajes: Python, Go.") == ("Python",)
    assert _encontradas(".NET", cv="Experiencia en ASP.NET y .NET Core.") == (".NET",)


def test_un_cv_sin_texto_no_menciona_nada() -> None:
    assert coincidir("", ["Python", "SQL"]) == Coincidencia(
        encontradas=(), faltantes=("Python", "SQL")
    )


def test_normalizar_deja_un_solo_espacio_y_quita_acentos() -> None:
    assert normalizar("  Atención\tal   CLIENTE_final ") == "atencion al cliente final"
    assert normalizar("Node.js / C++ / C#") == "node.js / c++ / c#"


def test_skills_validas_como_las_pide_la_base() -> None:
    assert skills_validas(["Python"] * MAX_SKILLS)
    assert not skills_validas(["Python"] * (MAX_SKILLS + 1))
    assert not skills_validas(["  "])
    assert not skills_validas(["x" * 61])
    assert skills_validas([])


@pytest.mark.parametrize("grupo", SINONIMOS, ids=lambda g: g[0])
def test_los_sinonimos_ya_estan_normalizados(grupo: tuple[str, ...]) -> None:
    for forma in grupo:
        assert normalizar(forma) == forma


def test_un_cv_escaneado_no_es_legible() -> None:
    """pypdf no hace OCR: de un escaneo sale poco o nada."""
    assert es_legible(CV)
    assert not es_legible("")
    assert not es_legible("1 2 3 4 5 6 7 8 9 0 . , ; :" * 20)  # sin letras
    assert es_legible("a" * MIN_LETRAS_LEGIBLES)
    assert not es_legible("a" * (MIN_LETRAS_LEGIBLES - 1))
