"""Límites de cada plan (ADR-017). El contrato compartido está en `test_contrato_limites_plan.py`."""

from __future__ import annotations

import pytest

from app.domain.plan import (
    CupoDeAplicacionesLlenoError,
    LimiteDePublicacionesError,
    LimiteDeVacantesError,
    PlanSinIAError,
    limites_del_plan,
    verificar_ia,
)


def test_el_plan_gratis_solo_abre_el_career_site_y_la_etapa_aplicados() -> None:
    limites = limites_del_plan("gratis", tamano=30)
    assert limites.modulos == ("career-site",)
    assert limites.etapas_visibles == ("applied",)
    assert limites.vacantes_activas == 3
    assert limites.aplicaciones_por_vacante == 50


def test_el_plan_con_ia_no_tiene_topes() -> None:
    limites = limites_del_plan("ia", tamano=30, ajuste=2)
    assert limites.vacantes_activas is None
    assert limites.aplicaciones_por_vacante is None
    limites.verificar_publicacion(activas=1000)
    limites.verificar_publicacion_nueva(recientes=1000)
    limites.verificar_aplicacion(aplicaciones=1000)


def test_publicar_con_el_cupo_lleno_falla() -> None:
    limites = limites_del_plan("gratis", tamano=80)
    limites.verificar_publicacion(activas=3)
    with pytest.raises(LimiteDeVacantesError, match="4 de 4"):
        limites.verificar_publicacion(activas=4)


def test_la_aplicacion_51_no_entra() -> None:
    limites = limites_del_plan("gratis")
    limites.verificar_aplicacion(aplicaciones=49)
    with pytest.raises(CupoDeAplicacionesLlenoError):
        limites.verificar_aplicacion(aplicaciones=50)


def test_la_ia_solo_corre_con_el_plan_con_ia() -> None:
    verificar_ia("ia")
    with pytest.raises(PlanSinIAError, match="el plan gratis no incluye los servicios de IA"):
        verificar_ia("gratis")


@pytest.mark.parametrize("plan", [None, "", "pro", "IA"])
def test_un_plan_desconocido_no_corre_ia(plan: str | None) -> None:
    with pytest.raises(PlanSinIAError):
        verificar_ia(plan)


def test_cerrar_y_publicar_otra_no_da_vacantes_sin_fin() -> None:
    """En la ventana se publican tantas nuevas como activas: aquí, 3."""
    limites = limites_del_plan("gratis", tamano=30)
    limites.verificar_publicacion_nueva(recientes=2)
    with pytest.raises(LimiteDePublicacionesError, match="3 de 3 vacantes publicadas"):
        limites.verificar_publicacion_nueva(recientes=3)
