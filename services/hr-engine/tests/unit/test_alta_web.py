"""Las reglas del registro de la web: opciones, LinkedIn, cupo, IP y la URL de verificación."""

from __future__ import annotations

from urllib.parse import unquote, urlsplit

import pytest

from app.domain.alta import SolicitudInvalidaError
from app.domain.alta_web import (
    PISO_DEL_RANGO,
    SolicitudDeAltaWeb,
    hash_de_ip,
    ip_valida,
    url_de_verificacion,
)
from app.domain.plan import limite_de_vacantes


def datos(**cambios: object) -> dict[str, object]:
    base: dict[str, object] = {
        "lead_id": "1024",
        "nombre": "  Ana   Ruiz ",
        "correo": " Ana@FerreteriaNorte.mx ",
        "publica_para": "propia",
        "empresa": "Ferretería Norte",
        "cargo": "Jefa de RH",
        "web_empresa": "https://ferreterianorte.mx",
        "linkedin": None,
        "verificacion": "dominio",
        "pais": "mx",
        "tamano": "16-50",
        "sector": "comercio",
        "contrataciones_mes": "3-5",
        "puestos": ["ventas", "operativos", "ventas"],
        "origen": "linkedin",
        "utm_medium": "social",
        "utm_campaign": "lanzamiento",
        "ip": "203.0.113.7",
    }
    return {**base, **cambios}


def nueva(**cambios: object) -> SolicitudDeAltaWeb:
    return SolicitudDeAltaWeb.nueva(**datos(**cambios))  # type: ignore[arg-type]


def test_normaliza_el_registro_de_la_web() -> None:
    solicitud = nueva()
    assert solicitud.correo == "ana@ferreterianorte.mx"
    assert solicitud.alta.nombre == "Ana Ruiz"
    assert solicitud.alta.empresa == "Ferretería Norte"
    assert solicitud.puestos == ("ventas", "operativos")
    assert solicitud.ip == "203.0.113.7"


@pytest.mark.parametrize(
    ("rango", "cupo"), [("1-15", 3), ("16-50", 3), ("51-200", 4), ("200+", 4), (None, 3)]
)
def test_el_rango_da_el_cupo_del_plan_gratis(rango: str | None, cupo: int) -> None:
    # Reclutador independiente: sin tamaño. Su LinkedIn personal es obligatorio.
    cambios: dict[str, object] = {"tamano": rango}
    if rango is None:
        cambios |= {"publica_para": "clientes", "linkedin": "https://www.linkedin.com/in/ana"}
    solicitud = nueva(**cambios)
    assert limite_de_vacantes(solicitud.alta.tamano) == cupo


def test_el_piso_de_cada_rango_esta_en_el_rango() -> None:
    for rango, piso in PISO_DEL_RANGO.items():
        assert str(piso) == rango.split("-")[0].rstrip("+")


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("publica_para", "agencia"),
        ("verificacion", "manual"),
        ("pais", "co"),
        ("tamano", "10-20"),
        ("sector", "mineria"),
        ("contrataciones_mes", "muchas"),
        ("puestos", ["ventas", "pilotos"]),
    ],
)
def test_solo_acepta_las_opciones_del_formulario(campo: str, valor: object) -> None:
    with pytest.raises(SolicitudInvalidaError):
        nueva(**{campo: valor})


@pytest.mark.parametrize("lead_id", ["", " ", "con espacio", "x" * 65])
def test_el_lead_id_es_corto_y_sin_espacios(lead_id: str) -> None:
    with pytest.raises(SolicitudInvalidaError):
        nueva(lead_id=lead_id)


@pytest.mark.parametrize(
    "url",
    ["http://ferreterianorte.mx", "ferreterianorte.mx", "https://localhost", "https://a b.mx"],
)
def test_la_web_de_la_empresa_tiene_que_ser_https(url: str) -> None:
    with pytest.raises(SolicitudInvalidaError):
        nueva(web_empresa=url)


def test_el_linkedin_tiene_que_ser_de_linkedin() -> None:
    with pytest.raises(SolicitudInvalidaError):
        nueva(linkedin="https://linkedin.com.estafa.mx/in/ana")
    assert nueva(linkedin="https://mx.linkedin.com/company/ferreteria").linkedin


def test_la_empresa_da_su_web_o_su_linkedin() -> None:
    with pytest.raises(SolicitudInvalidaError):
        nueva(web_empresa=None, linkedin=None)
    assert nueva(web_empresa=None, linkedin="https://www.linkedin.com/company/fn").linkedin


def test_el_reclutador_independiente_da_su_linkedin_personal() -> None:
    with pytest.raises(SolicitudInvalidaError):
        nueva(publica_para="clientes", tamano=None, linkedin=None)
    with pytest.raises(SolicitudInvalidaError):
        nueva(
            publica_para="clientes",
            tamano=None,
            linkedin="https://www.linkedin.com/company/agencia",
        )
    assert nueva(
        publica_para="clientes", tamano=None, linkedin="https://www.linkedin.com/in/ana-ruiz"
    ).linkedin


def test_un_campo_de_texto_largo_no_pasa() -> None:
    with pytest.raises(SolicitudInvalidaError):
        nueva(cargo="x" * 121)
    with pytest.raises(SolicitudInvalidaError):
        nueva(utm_campaign="x" * 101)


def test_la_ip_se_guarda_con_hash_y_solo_si_es_una_ip() -> None:
    assert ip_valida("no-es-una-ip") is None
    assert ip_valida(" 2001:db8::1 ") == "2001:db8::1"
    assert nueva(ip="no-es-una-ip").ip is None
    uno = hash_de_ip("203.0.113.7", "secreto")
    assert uno == hash_de_ip("203.0.113.7", "secreto")
    assert uno != hash_de_ip("203.0.113.7", "otro-secreto")
    assert uno is not None and "203.0.113.7" not in uno
    assert hash_de_ip(None, "secreto") is None


def test_el_correo_va_en_el_fragmento_y_no_en_la_query() -> None:
    url = url_de_verificacion("https://panel.vectorhrtech.com/", "ana+rh@ferreterianorte.mx")
    partes = urlsplit(url)
    assert (partes.scheme, partes.netloc, partes.path, partes.query) == (
        "https",
        "panel.vectorhrtech.com",
        "/verificar",
        "",
    )
    assert partes.fragment == "correo=ana%2Brh%40ferreterianorte.mx"
    assert unquote(partes.fragment.removeprefix("correo=")) == "ana+rh@ferreterianorte.mx"
