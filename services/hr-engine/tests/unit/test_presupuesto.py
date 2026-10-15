"""Presupuesto de gasto por run (ADR-005): suma, desglose y tope opcional."""

from __future__ import annotations

import pytest

from app.domain.presupuesto import CostBudget, CostCapExceededError


def test_suma_el_gasto_y_lo_desglosa_por_paso() -> None:
    presupuesto = CostBudget(cap_usd=0.05)
    presupuesto.add(0.001, "embedding_icp")
    presupuesto.add(0.002, "scoring")
    presupuesto.add(0.003, "scoring")

    assert presupuesto.spent_usd == pytest.approx(0.006)
    assert presupuesto.breakdown == pytest.approx({"embedding_icp": 0.001, "scoring": 0.005})


def test_con_el_tope_activo_corta_al_alcanzarlo() -> None:
    presupuesto = CostBudget(cap_usd=0.01, enforce=True)
    presupuesto.add(0.005)
    presupuesto.assert_under_cap()

    # 0.005 + 0.005 es 0.01 exacto en coma flotante (0.009 + 0.001 no lo es).
    presupuesto.add(0.005)
    with pytest.raises(CostCapExceededError):
        presupuesto.assert_under_cap()


def test_con_el_tope_apagado_solo_mide() -> None:
    presupuesto = CostBudget(cap_usd=0.01, enforce=False)
    presupuesto.add(1.0)

    presupuesto.assert_under_cap()
    assert presupuesto.spent_usd == 1.0


def test_lo_que_queda_nunca_es_negativo() -> None:
    presupuesto = CostBudget(cap_usd=0.01, enforce=False)
    presupuesto.add(0.004)
    assert presupuesto.remaining_usd == pytest.approx(0.006)

    presupuesto.add(1.0)
    assert presupuesto.remaining_usd == 0.0
