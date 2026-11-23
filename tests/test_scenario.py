"""Scenario decomposition and the Scope 2 dual figure.

The decomposition is the kind of arithmetic that looks right and is not: a first
version used the new quantity in the factor term, double-counted the interaction,
and produced a plausible number that did not reconcile. These tests pin the
identity, not the formula's appearance.
"""

from __future__ import annotations

import pytest

from ghg.scenario import (
    ContractualInstrument,
    Scope2Dual,
    annual_quantity,
    classify_change,
    decompose,
)


def test_decomposition_reconciles_for_arbitrary_inputs():
    """The three effects must sum to the observed change for any inputs, not just
    the convenient one. This is the test the broken version failed."""
    import random

    random.seed(7)
    for _ in range(200):
        q_old = random.uniform(0.0, 5000.0)
        q_new = random.uniform(0.0, 5000.0)
        f_old = random.uniform(0.001, 10.0)
        f_new = random.uniform(0.001, 10.0)
        d = decompose("s", q_old, q_new, f_old, f_new)
        assert d.reconciles(), (q_old, q_new, f_old, f_new)


def test_pure_activity_change_has_no_factor_effect():
    """Same factor both years: everything is the plant's doing.

    200 kWh x 0.5 kg/kWh = 100 kg = 0.1 t. The /1000 is the kg -> tonne step and
    is easy to drop; these tests assert tonnes.
    """
    d = decompose("grid", 1000.0, 1200.0, 0.5, 0.5)
    assert d.activity_effect == pytest.approx(0.1)
    assert d.factor_effect == pytest.approx(0.0)
    assert classify_change(d) == "activity"


def test_pure_factor_change_has_no_activity_effect():
    """Same consumption, different factor: nothing physical changed.

    This is the case a totals-only report reads as a reduction. 1000 kWh at
    0.66 -> 0.62 kg/kWh is 0.66 -> 0.62 t: the drop is entirely the grid.
    """
    d = decompose("grid", 1000.0, 1000.0, 0.66, 0.62)
    assert d.activity_effect == pytest.approx(0.0)
    assert d.factor_effect == pytest.approx(-0.04)
    assert d.total_change == pytest.approx(-0.04)
    assert classify_change(d) == "factor"


def test_both_changes_produce_an_interaction_term():
    """Growth plus a falling factor: activity up, factor down, interaction negative.

    100 kWh x 0.66 = 66 kg = 0.066 t;  1000 x -0.04 = -40 kg = -0.04 t;
    100 x -0.04 = -4 kg = -0.004 t;  sum 22 kg = 0.022 t.
    """
    d = decompose("grid", 1000.0, 1100.0, 0.66, 0.62)
    assert d.activity_effect == pytest.approx(0.066)
    assert d.factor_effect == pytest.approx(-0.040)
    assert d.interaction == pytest.approx(-0.004)
    assert d.total_change == pytest.approx(0.022)


def test_the_real_shipped_years_reconcile():
    """The 2024 -> 2025 comparison in the repo: grid consumption up, grid factor down.

    2024: 3,216,000 kWh x 0.6592 = 2,119,987 kg  = 2,119.99 t
    2025: 3,456,000 kWh x 0.6187 = 2,138,227 kg  = 2,138.23 t
    change +18.24 t, of which +158.21 activity, -130.25 factor, -9.72 interaction.
    """
    d = decompose("grid_electricity", 3_216_000.0, 3_456_000.0, 0.6592, 0.6187)
    assert d.total_change == pytest.approx(18.24, abs=0.01)
    assert d.activity_effect == pytest.approx(158.21, abs=0.01)
    assert d.factor_effect == pytest.approx(-130.25, abs=0.01)
    assert d.reconciles()
    # the plant grew; the total barely moved. Both must appear in any honest summary.
    assert d.activity_effect > 0 and d.factor_effect < 0


def test_no_change_is_reported_as_such():
    d = decompose("x", 1000.0, 1000.0, 0.5, 0.5)
    assert classify_change(d) == "no change"
    assert d.total_change == pytest.approx(0.0)


def test_gwp_and_mass_multiplier_fold_into_the_effective_factor():
    """A gram-based methane factor must scale the same way CO2 does."""
    d = decompose("diesel", 1000.0, 1000.0, 0.000361, 0.000361, gwp=27.0)
    assert d.tco2e_new == pytest.approx(1000.0 * 0.000361 * 27.0 / 1000.0)


def test_annual_quantity_sums_only_the_requested_year():
    from ghg.activity import ActivityRecord

    records = [
        ActivityRecord("2024-01", "P", "grid", 100.0, "kWh", 2),
        ActivityRecord("2024-06", "P", "grid", 200.0, "kWh", 3),
        ActivityRecord("2025-01", "P", "grid", 400.0, "kWh", 4),
    ]
    assert annual_quantity(records, "grid", 2024) == pytest.approx(300.0)
    assert annual_quantity(records, "grid", 2025) == pytest.approx(400.0)
    assert annual_quantity(records, "grid", 2023) == 0.0


# ------------------------------------------------------------ Scope 2 methods


def test_location_and_market_are_equal_without_instruments():
    dual = Scope2Dual(
        consumption_kwh=1000.0,
        grid_factor_kg_per_kwh=0.5,
        instruments=(),
        residual_factor_kg_per_kwh=0.5,
    )
    assert dual.market_tco2e == pytest.approx(dual.location_tco2e)
    assert "not a reduction" in dual.describe()


def test_zero_carbon_instrument_lowers_the_market_figure():
    """A PPA at 0 kg/kWh covering half the load halves the market-based figure.

    1000 kWh, grid 0.5, 500 kWh at 0.0, residual 0.5:
        location = 1000*0.5/1000 = 0.5 t
        market   = 0 + 500*0.5/1000 = 0.25 t
    """
    dual = Scope2Dual(
        consumption_kwh=1000.0,
        grid_factor_kg_per_kwh=0.5,
        instruments=(ContractualInstrument("wind PPA", 0.5, 0.0),),
        residual_factor_kg_per_kwh=0.5,
    )
    assert dual.location_tco2e == pytest.approx(0.5)
    assert dual.market_tco2e == pytest.approx(0.25)
    assert dual.coverage == pytest.approx(0.5)


def test_instruments_exceeding_consumption_are_rejected():
    """Certificates cannot cover more electricity than was bought: that is how a
    market-based figure is gamed, and the model refuses it."""
    dual = Scope2Dual(
        consumption_kwh=1000.0,
        grid_factor_kg_per_kwh=0.5,
        instruments=(ContractualInstrument("oversized", 5.0, 0.0),),
        residual_factor_kg_per_kwh=0.5,
    )
    with pytest.raises(ValueError, match="cannot exceed"):
        _ = dual.residual_kwh


def test_negative_instrument_inputs_are_rejected():
    with pytest.raises(ValueError, match="mwh must be"):
        ContractualInstrument("bad", -1.0, 0.0)
    with pytest.raises(ValueError, match="emission factor must be"):
        ContractualInstrument("bad", 1.0, -0.5)


def test_unnamed_instrument_is_rejected():
    """An unnamed certificate cannot be shown to a verifier."""
    with pytest.raises(ValueError, match="must be named"):
        ContractualInstrument("   ", 1.0, 0.0)
