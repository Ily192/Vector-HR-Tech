"""Lo que se quita del CV antes de mandarlo al modelo (ADR-021 §3)."""

from __future__ import annotations

import pytest

from app.domain.anonimizacion import (
    CORREO,
    ENLACE,
    MAX_CARACTERES,
    NOMBRE,
    TELEFONO,
    anonimizar,
)

CV = """MARÍA JOSÉ DE LA CRUZ PÉREZ
maria.cruz@correo.test · +52 (55) 1234-5678 · linkedin.com/in/maria-cruz
Edad: 34 años
Estado civil: Casada
• Nacionalidad: Mexicana
Dirección: Av. Reforma 123, CDMX
CURP: CUPM900312MDFRRR08

Experiencia
Coordinadora de almacén, Grupo Norte (2018 - 2022)
Dirección de proyectos de inventario: bajé las mermas 12% en 2021.
Portafolio: https://mariacruz.dev/proyectos
"""


def _texto(cv: str = CV, nombre: str | None = "María José de la Cruz Pérez") -> str:
    return anonimizar(cv, nombre=nombre, correo="maria.cruz@correo.test").texto


def test_quita_el_nombre_y_cada_una_de_sus_partes_sin_importar_acentos_ni_mayusculas() -> None:
    texto = _texto()
    for parte in ("María", "MARÍA", "José", "JOSÉ", "Cruz", "CRUZ", "Pérez", "PÉREZ"):
        assert parte not in texto
    assert texto.startswith(NOMBRE)


def test_las_particulas_del_nombre_se_quedan_porque_son_palabras_comunes() -> None:
    texto = _texto("Ana de la Paz: líder de la planta de Monterrey", nombre="Ana de la Paz")
    assert texto == f"{NOMBRE} de la {NOMBRE}: líder de la planta de Monterrey"


def test_una_parte_de_dos_letras_solo_se_quita_tal_como_se_escribe() -> None:
    texto = _texto("Wei Li. Implementé linters y libretas de control.", nombre="Wei Li")
    assert texto == f"{NOMBRE}. Implementé linters y libretas de control."


def test_quita_correo_telefono_y_enlaces() -> None:
    texto = _texto()
    assert "maria.cruz@correo.test" not in texto
    assert "1234-5678" not in texto
    assert "linkedin.com" not in texto
    assert "mariacruz.dev" not in texto
    for marca in (CORREO, TELEFONO, ENLACE):
        assert marca in texto


@pytest.mark.parametrize(
    "telefono",
    ["+58 412-123-4567", "0412 1234567", "(55) 1234 5678", "5512345678", "+57 300 123 4567"],
)
def test_reconoce_los_telefonos_de_la_region(telefono: str) -> None:
    assert _texto(f"Llámame al {telefono} cuando quieras.", nombre=None) == (
        f"Llámame al {TELEFONO} cuando quieras."
    )


@pytest.mark.parametrize(
    "cifra",
    ["2018 - 2022", "2015-2019", "2019\u20132020 · 2021", "25 000 000", "12%", "3 años"],
)
def test_no_confunde_fechas_ni_cifras_con_un_telefono(cifra: str) -> None:
    assert _texto(f"Dato: {cifra}.", nombre=None) == f"Dato: {cifra}."


def test_quita_las_lineas_de_datos_personales() -> None:
    texto = _texto()
    for dato in ("34 años", "Casada", "Mexicana", "Reforma", "CUPM900312"):
        assert dato not in texto


@pytest.mark.parametrize(
    "linea",
    [
        "Fecha de nacimiento: 12/03/1990",
        "SEXO: Femenino",
        "Género \u2013 Mujer",
        "Domicilio: Calle 5",
        "Hijos: 2",
        "Religión: Católica",
        "Cédula: V-12.345.678",
        "Pasaporte: G1234567",
        "Discapacidad: ninguna",
    ],
)
def test_reconoce_cada_etiqueta_de_datos_personales(linea: str) -> None:
    assert _texto(f"Analista de datos\n{linea}\nPython y SQL", nombre=None) == (
        "Analista de datos\nPython y SQL"
    )


def test_una_linea_sin_separador_no_es_de_datos_personales() -> None:
    """ "Dirección de proyectos" es experiencia, no un domicilio."""
    assert "Dirección de proyectos de inventario" in _texto()


def test_lo_que_importa_para_el_puesto_se_queda() -> None:
    texto = _texto()
    assert "Coordinadora de almacén, Grupo Norte (2018 - 2022)" in texto
    assert "bajé las mermas 12% en 2021" in texto


def test_marcas_seguidas_dicen_lo_mismo_que_una() -> None:
    assert _texto("Ana Paz, Paz. Gerente.", nombre="Ana Paz") == f"{NOMBRE}. Gerente."


def test_sin_nombre_tambien_quita_el_contacto() -> None:
    assert _texto("contacto: ana@correo.test", nombre=None) == f"contacto: {CORREO}"


def test_un_cv_largo_se_recorta_en_un_salto_de_linea() -> None:
    linea = "Responsable de inventarios cíclicos y conteos en el almacén central.\n"
    cv = anonimizar(linea * 400, nombre=None)
    assert cv.recortado
    assert len(cv.texto) <= MAX_CARACTERES
    assert cv.texto.endswith("almacén central.")


def test_un_cv_corto_no_se_recorta() -> None:
    cv = anonimizar("Analista de datos con Python.", nombre="Ana Paz")
    assert not cv.recortado
