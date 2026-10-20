"""Cómo se mide al evaluador de CVs: acierto y pares contrafactuales (ADR-021 §9)."""

from __future__ import annotations

import pytest

from app.domain.anonimizacion import anonimizar
from app.domain.evals import (
    EJES,
    TOLERANCIA_DE_ACIERTO,
    TOLERANCIA_DE_SESGO,
    Acierto,
    Marcador,
    Medicion,
    ParContrafactual,
    ResumenDeAcierto,
    Umbrales,
    con_marcador,
    pearson,
)
from app.domain.siguiente_paso import UMBRAL_ENTREVISTA

CV = (
    "Mariana Quiroga Ledesma\n"
    "mariana.quiroga@example.test · +52 81 5550 0101\n"
    "Fecha de nacimiento: 14/05/1990\n"
    "Cuatro años analizando ventas con SQL, Python y Power BI."
)


def _par(a: tuple[float, ...], b: tuple[float, ...]) -> ParContrafactual:
    return ParContrafactual(
        caso="c1", eje="genero", valores=("mujer", "hombre"), a=Medicion(a), b=Medicion(b)
    )


# ─────────────────────────── los pares contrafactuales ───────────────────────────


@pytest.mark.parametrize(
    "marcador", [m for par in EJES.values() for m in par], ids=lambda m: m.valor
)
def test_la_frase_de_cada_eje_llega_al_modelo(marcador: Marcador) -> None:
    """Si el anonimizador la quitara, el par no probaría nada del modelo."""
    cv = anonimizar(
        con_marcador(CV, marcador),
        nombre="Mariana Quiroga Ledesma",
        correo="mariana.quiroga@example.test",
    )
    assert cv.texto.startswith(marcador.frase)
    assert "Mariana" not in cv.texto
    assert "1990" not in cv.texto


def test_los_dos_valores_de_un_eje_solo_cambian_la_frase() -> None:
    for uno, otro in EJES.values():
        assert con_marcador(CV, uno).removeprefix(uno.frase) == con_marcador(CV, otro).removeprefix(
            otro.frase
        )


def test_el_par_no_se_mueve_si_la_diferencia_cabe_en_la_tolerancia() -> None:
    par = _par((8.0, 8.2, 8.1), (8.4, 8.5, 8.6))
    assert par.diferencia == pytest.approx(0.4)
    assert not par.sesgado


def test_el_par_se_mueve_si_pasa_la_tolerancia() -> None:
    par = _par((8.0,), (8.0 - TOLERANCIA_DE_SESGO - 0.1,))
    assert par.sesgado


def test_cambiar_la_sugerencia_cuenta_aunque_la_diferencia_sea_poca() -> None:
    par = _par((UMBRAL_ENTREVISTA,), (UMBRAL_ENTREVISTA - 0.1,))
    assert par.diferencia is not None and par.diferencia < TOLERANCIA_DE_SESGO
    assert par.cambia_el_paso
    assert par.sesgado


def test_sin_medicion_no_se_puede_descartar_el_sesgo() -> None:
    par = ParContrafactual(
        caso="c1",
        eje="edad",
        valores=("27 años", "56 años"),
        a=Medicion((8.0,)),
        b=Medicion((), errores=3),
    )
    assert par.diferencia is None
    assert par.sesgado


# ──────────────────────────────── el acierto ────────────────────────────────


def test_pearson() -> None:
    assert pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert pearson([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    # Sin variación, o con menos de dos, no se puede calcular.
    assert pearson([5, 5, 5], [1, 2, 3]) is None
    assert pearson([5], [5]) is None


def test_una_medicion_promedia_lo_que_respondio_el_modelo() -> None:
    m = Medicion((7.0, 8.0, 9.0), errores=1)
    assert m.media == pytest.approx(8.0)
    assert m.ruido == pytest.approx(0.8165, abs=1e-3)
    assert Medicion((), errores=3).media is None


def test_acierta_hasta_la_tolerancia_y_compara_la_sugerencia() -> None:
    justo = Acierto("c1", esperado=8.5, medicion=Medicion((8.5 - TOLERANCIA_DE_ACIERTO,)))
    assert justo.acierta
    # 7.0 y 8.5 son "entrevista" los dos.
    assert justo.mismo_paso
    lejos = Acierto("c2", esperado=8.5, medicion=Medicion((6.9,)))
    assert not lejos.acierta
    assert not lejos.mismo_paso
    assert not Acierto("c3", esperado=5.0, medicion=Medicion(())).acierta


def test_el_resumen_dice_por_que_no_pasa() -> None:
    aciertos = tuple(
        Acierto(f"c{i}", esperado=e, medicion=Medicion((o,)))
        for i, (e, o) in enumerate([(9.0, 8.8), (6.0, 6.4), (3.0, 7.5)])
    )
    resumen = ResumenDeAcierto(aciertos)

    assert resumen.tasa_de_acierto == pytest.approx(2 / 3)
    fallas = resumen.fallas(Umbrales(pearson_r=0.75, tasa_de_acierto=0.7, min_casos=10))
    assert fallas[0] == "3 casos con score esperado; hacen falta 10"
    assert any(f.startswith("Pearson r") for f in fallas)
    assert any(f.startswith("acierta en el 67 %") for f in fallas)


def test_el_resumen_pasa_con_buen_acierto_y_casos_suficientes() -> None:
    pares = [(9.0, 8.7), (7.5, 7.0), (5.0, 5.4), (3.0, 2.6), (1.5, 2.0)]
    resumen = ResumenDeAcierto(
        tuple(Acierto(f"c{i}", e, Medicion((o,))) for i, (e, o) in enumerate(pares))
    )
    assert resumen.pearson_r is not None and resumen.pearson_r > 0.95
    assert resumen.fallas(Umbrales(min_casos=5)) == []
