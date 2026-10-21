"""El correo de resumen de los diagnósticos gratuitos (migración 0017): qué dice y qué no."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.domain.diagnostico import (
    Diagnostico,
    resumen,
    top_procesos,
    una_linea,
)

PARA = "hola@vectorhrtech.com"


def _resultado(**cambios: Any) -> dict[str, Any]:
    resultado: dict[str, Any] = {
        "version": 1,
        "procesos": [
            {
                "id": "nomina",
                "nombre": "Nómina",
                "horasSemana": 12,
                "etapa": "Automatizar",
                "horasRecuperablesMes": 31.2,
            },
            {
                "id": "reclutamiento",
                "nombre": "Reclutamiento",
                "horasSemana": 8,
                "etapa": "Optimizar",
                "horasRecuperablesMes": 20.8,
            },
            {
                "id": "vacaciones",
                "nombre": "Vacaciones y permisos",
                "horasSemana": 4,
                "etapa": "Digitalizar",
                "horasRecuperablesMes": 10.4,
            },
            {
                "id": "onboarding",
                "nombre": "Onboarding",
                "horasSemana": 2,
                "etapa": "Digitalizar",
                "horasRecuperablesMes": 5.2,
            },
        ],
        "horasRecuperablesMes": 67.6,
        "horasRecuperablesAnio": 811.2,
    }
    resultado.update(cambios)
    return resultado


def diagnostico(**cambios: Any) -> Diagnostico:
    datos: dict[str, Any] = {
        "id": uuid4(),
        "creado_en": datetime(2026, 10, 21, 15, 4, tzinfo=UTC),
        "nombre": "Mariana Ruiz",
        "empresa": "Andes Logística",
        "correo": "mariana@andes.test",
        "origen": "linkedin",
        "utm_medium": "cpc",
        "utm_campaign": "diagnostico-octubre",
        "horas_recuperables_mes": 67.6,
        "resultado": _resultado(),
        "ip": "203.0.113.7",
        "turnstile_token": "token-valido",
        "verificado": False,
    }
    datos.update(cambios)
    return Diagnostico(**datos)


def test_el_correo_de_un_diagnostico_trae_todo_lo_que_vector_hr_necesita() -> None:
    d = diagnostico()
    correo = resumen(PARA, [d], 0)

    assert correo is not None
    assert correo.para == PARA
    assert correo.asunto == "Nuevo diagnóstico: Andes Logística"
    for linea in (
        "Empresa: Andes Logística",
        "Nombre: Mariana Ruiz",
        "Correo: mariana@andes.test",
        "Origen: linkedin / cpc / diagnostico-octubre",
        "Horas recuperables al mes: 67.6",
        "Horas recuperables al año: 811.2",
        "  1. Nómina (Automatizar): 31.2 h al mes",
        "  2. Reclutamiento (Optimizar): 20.8 h al mes",
        "  3. Vacaciones y permisos (Digitalizar): 10.4 h al mes",
        "Fecha: 2026-10-21 15:04 UTC",
        f"Id: {d.id}",
    ):
        assert linea in correo.cuerpo.splitlines(), linea
    # Solo el top 3.
    assert "Onboarding" not in correo.cuerpo


def test_sin_utm_dice_que_llego_directo() -> None:
    correo = resumen(PARA, [diagnostico(origen=None, utm_medium=None, utm_campaign=None)], 0)
    assert correo is not None
    assert "Origen: directo (sin utm)" in correo.cuerpo


def test_nada_que_avisar_no_es_un_correo() -> None:
    assert resumen(PARA, [], 0) is None


def test_varios_van_en_un_solo_correo_y_los_del_tope_en_una_linea() -> None:
    correo = resumen(PARA, [diagnostico(), diagnostico(empresa="Siete Mares")], 3)

    assert correo is not None
    assert correo.asunto == "Nuevos diagnósticos: 5"
    assert "Empresa: Andes Logística" in correo.cuerpo
    assert "Empresa: Siete Mares" in correo.cuerpo
    assert correo.cuerpo.rstrip().endswith("y 3 diagnósticos más (revísalos en la base)")


def test_solo_los_del_tope() -> None:
    correo = resumen(PARA, [], 1)
    assert correo is not None
    assert correo.asunto == "Nuevos diagnósticos: 1"
    assert "Empresa:" not in correo.cuerpo
    assert "y 1 diagnóstico más (revísalos en la base)" in correo.cuerpo


def test_el_asunto_es_una_linea_aunque_la_empresa_traiga_saltos() -> None:
    """Una cabecera con salto de línea inyecta cabeceras (Bcc, otro cuerpo)."""
    malicioso = "ACME\r\nBcc: victima@x.test\r\n\r\nOtro cuerpo" + "x" * 200
    correo = resumen(PARA, [diagnostico(empresa=malicioso)], 0)

    assert correo is not None
    assert "\n" not in correo.asunto and "\r" not in correo.asunto
    assert correo.asunto.startswith("Nuevo diagnóstico: ACME Bcc: victima@x.test Otro cuerpo")
    assert len(correo.asunto) <= len("Nuevo diagnóstico: ") + 60


def test_los_datos_del_prospecto_no_rompen_las_lineas_del_cuerpo() -> None:
    correo = resumen(
        PARA, [diagnostico(nombre="Ana\nEmpresa: Falsa\u2028\x00", utm_campaign="a\tb")], 0
    )
    assert correo is not None
    assert "Nombre: Ana Empresa: Falsa" in correo.cuerpo.splitlines()
    assert [linea for linea in correo.cuerpo.splitlines() if linea.startswith("Empresa:")] == [
        "Empresa: Andes Logística"
    ]
    assert "\x00" not in correo.cuerpo and "\t" not in correo.cuerpo


def test_un_resultado_roto_no_tumba_el_aviso() -> None:
    for roto in (
        {},
        {"procesos": "no es una lista"},
        {"procesos": [None, 3, {"nombre": "Sin horas"}, {"horasRecuperablesMes": 4}]},
        {"procesos": [{"nombre": "Infinito", "horasRecuperablesMes": float("inf")}]},
        {"procesos": [{"nombre": "Booleano", "horasRecuperablesMes": True}]},
        {"horasRecuperablesAnio": "mucho"},
    ):
        correo = resumen(PARA, [diagnostico(resultado=roto)], 0)
        assert correo is not None
        assert "Procesos que más tiempo le quitan" not in correo.cuerpo
        assert "al año" not in correo.cuerpo


def test_top_procesos_salta_los_invalidos_y_se_queda_con_tres() -> None:
    resultado = _resultado()
    resultado["procesos"].insert(0, {"nombre": "", "horasRecuperablesMes": 99})
    assert [p.nombre for p in top_procesos(resultado)] == [
        "Nómina",
        "Reclutamiento",
        "Vacaciones y permisos",
    ]


def test_una_linea_recorta_con_puntos_suspensivos() -> None:
    assert una_linea("a" * 10, 5) == "aaaa…"
    assert una_linea("  hola \n  mundo ") == "hola mundo"
