"""Reglas del alta de empresas que no dependen de la base (`domain/alta.py`)."""

from __future__ import annotations

import hashlib
import re

import pytest

from app.domain.alta import (
    MAX_LARGO_DEL_NOMBRE,
    SolicitudDeAlta,
    SolicitudInvalidaError,
    hash_del_token,
    nuevo_token,
    slug_de_empresa,
)

DATOS = {"empresa": "Ferretería Norte", "correo": "ana@ferreterianorte.mx", "nombre": "Ana Ruiz"}


def test_normaliza_el_correo_y_los_espacios() -> None:
    solicitud = SolicitudDeAlta.nueva(
        empresa="  Ferretería   Norte ",
        correo=" Ana.Ruiz@FerreteriaNorte.MX ",
        nombre=" Ana  Ruiz ",
        tamano=35,
    )
    assert (solicitud.empresa, solicitud.correo, solicitud.nombre) == (
        "Ferretería Norte",
        "ana.ruiz@ferreterianorte.mx",
        "Ana Ruiz",
    )
    assert (solicitud.tamano, solicitud.rol) == (35, "HR")


@pytest.mark.parametrize(
    ("campos", "mensaje"),
    [
        ({"empresa": "   "}, "nombre de la empresa"),
        ({"empresa": "x" * (MAX_LARGO_DEL_NOMBRE + 1)}, "nombre de la empresa"),
        ({"nombre": ""}, "nombre de la persona"),
        ({"correo": "ana@"}, "correo"),
        ({"correo": "ana ruiz@ferreterianorte.mx"}, "correo"),
        ({"tamano": 0}, "tamaño"),
        ({"rol": "SuperAdmin"}, "rol"),
    ],
)
def test_rechaza_lo_que_no_sirve(campos: dict[str, object], mensaje: str) -> None:
    with pytest.raises(SolicitudInvalidaError, match=mensaje):
        SolicitudDeAlta.nueva(**{**DATOS, **campos})  # type: ignore[arg-type]


def test_direccion_tambien_se_puede_invitar() -> None:
    assert SolicitudDeAlta.nueva(**DATOS, rol="Director").rol == "Director"


def test_el_slug_va_sin_acentos_ni_signos_y_el_sufijo_lo_desempata() -> None:
    assert slug_de_empresa("Ferretería Norte, S.A. de C.V.") == "ferreteria-norte-s-a-de-c-v"
    assert slug_de_empresa("Ferretería Norte", "3f9a") == "ferreteria-norte-3f9a"
    assert slug_de_empresa("x" * 90, "3f9a") == f"{'x' * 50}-3f9a"
    assert re.fullmatch(r"[0-9a-f]{4}", slug_de_empresa("¿?"))


def test_el_hash_es_el_que_compara_handle_new_user() -> None:
    # 0003: `encode(sha256(invite_token::bytea), 'hex')`, el sha256 de los bytes del token.
    assert hash_del_token("abc") == hashlib.sha256(b"abc").hexdigest()
    assert hash_del_token("abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_el_token_es_largo_unico_y_sin_barras_invertidas() -> None:
    # Una barra invertida cambiaría el `::bytea` de Postgres y el hash no coincidiría.
    token = nuevo_token()
    assert len(token) >= 43
    assert re.fullmatch(r"[A-Za-z0-9_-]+", token)
    assert nuevo_token() != token
