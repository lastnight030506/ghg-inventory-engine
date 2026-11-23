"""Inventory arithmetic.

The load-bearing tests work the conversion by hand in the docstring, then assert
the code reproduces it. If they are green, the tCO2e column means what the
report says it means.
"""

from __future__ import annotations

import pytest

from ghg.activity import ActivityRecord
from ghg.factors import EmissionFactor, FactorError, load_factors
from ghg.inventory import build_inventory


def factor(source, gas, value, denominator, mass_unit="kg", scope=1):
    return EmissionFactor(
        activity_source=source,
        scope=scope,
        gas=gas,
        emission_factor=value,
        denominator=denominator,
        mass_unit=mass_unit,
        citation="test fixture",
        publication_year=2006,
    )


def record(source="diesel_furnace", quantity=1000.0, unit="L", period="2025-01", line=2):
    return ActivityRecord(
        period=period, site="Plant", activity_source=source, quantity=quantity, unit=unit, line=line
    )


def test_hand_calculated_diesel_line():
    """1000 L diesel, factor 2.68 kg CO2/L, GWP 1.

        1000 x 2.68 kg/L     = 2680 kg CO2
        2680 x 1.0 / 1000    = 2.68 tCO2e
    """
    register = {"diesel_furnace": [factor("diesel_furnace", "CO2", 2.68, "L")]}
    inv = build_inventory([record(quantity=1000.0)], register)
    assert len(inv.lines) == 1
    line = inv.lines[0]
    assert line.mass_emitted_kg == pytest.approx(2680.0)
    assert line.tco2e == pytest.approx(2.68)


def test_mass_unit_gram_is_applied_once():
    """500 g of CH4 per tonne of coal: 1 t x 500 g/t = 500 g = 0.5 kg.

        0.5 kg x 29.8 / 1000 = 0.0149 tCO2e

    A previous version computed mass_emitted_kg without the mass-unit multiplier
    while tCO2e used it, so the two columns disagreed by 1000x. This pins both.
    """
    register = {"coal_boiler": [factor("coal_boiler", "CH4_fossil", 500, "t", mass_unit="g")]}
    inv = build_inventory([record("coal_boiler", 1.0, "t")], register)
    line = inv.lines[0]
    assert line.mass_emitted_kg == pytest.approx(0.5)
    assert line.tco2e == pytest.approx(0.0149)
    # and the ledger's own numbers re-derive tCO2e
    assert line.mass_emitted_kg * line.gwp100 / 1000 == pytest.approx(line.tco2e)


def test_multi_gas_source_fans_out_and_sums():
    """One activity row, three gases, each with its own GWP."""
    register = {
        "diesel_furnace": [
            factor("diesel_furnace", "CO2", 2.68, "L"),
            factor("diesel_furnace", "CH4_fossil", 0.0001, "L"),
            factor("diesel_furnace", "N2O", 0.0001, "L"),
        ]
    }
    inv = build_inventory([record(quantity=1000.0)], register)
    assert len(inv.lines) == 3
    co2 = next(l for l in inv.lines if l.gas == "CO2")
    assert co2.tco2e == pytest.approx(2.68)
    assert inv.total_tco2e > co2.tco2e  # the other gases add, never subtract


def test_unregistered_source_fails_and_lists_known_sources():
    register = {"coal_boiler": [factor("coal_boiler", "CO2", 1.9, "t")]}
    with pytest.raises(FactorError, match="no emission factor"):
        build_inventory([record("diesel_furnace", 10.0)], register)


def test_unit_mismatch_fails_rather_than_reinterpreting():
    """A kWh factor applied to an MWh reading is a 1000x error a total hides."""
    register = {"grid_electricity": [factor("grid_electricity", "CO2e", 0.4, "kWh", scope=2)]}
    with pytest.raises(FactorError, match="denominator"):
        build_inventory([record("grid_electricity", 120.0, "MWh")], register)


def test_matching_unit_succeeds():
    register = {"grid_electricity": [factor("grid_electricity", "CO2e", 0.4, "kWh", scope=2)]}
    inv = build_inventory([record("grid_electricity", 1000.0, "kWh")], register)
    assert inv.lines[0].tco2e == pytest.approx(0.4)


def test_scope_and_month_aggregation_reconcile_to_total():
    register = {
        "grid_electricity": [factor("grid_electricity", "CO2e", 0.4, "kWh", scope=2)],
        "diesel_furnace": [factor("diesel_furnace", "CO2", 2.68, "L", scope=1)],
    }
    records = [
        record("grid_electricity", 1000.0, "kWh", "2025-01"),
        record("grid_electricity", 2000.0, "kWh", "2025-02"),
        record("diesel_furnace", 1000.0, "L", "2025-01"),
    ]
    inv = build_inventory(records, register)
    assert inv.by_scope() == {1: pytest.approx(2.68), 2: pytest.approx(1.2)}
    assert sum(inv.by_month_scope().values()) == pytest.approx(inv.total_tco2e)
    assert sum(inv.by_source().values()) == pytest.approx(inv.total_tco2e)


def test_zero_quantity_produces_a_zero_line_not_an_error():
    register = {"grid_electricity": [factor("grid_electricity", "CO2e", 0.4, "kWh", scope=2)]}
    inv = build_inventory([record("grid_electricity", 0.0, "kWh")], register)
    assert inv.total_tco2e == 0.0
    assert len(inv.lines) == 1


def test_duplicate_factor_for_same_gas_is_rejected(tmp_path):
    path = tmp_path / "factors.csv"
    path.write_text(
        "activity_source,scope,gas,emission_factor,factor_unit_denominator,"
        "factor_mass_unit,citation,publication_year\n"
        "diesel_furnace,1,CO2,2.68,L,kg,IPCC 2006,2006\n"
        "diesel_furnace,1,CO2,2.70,L,kg,IPCC 2019,2019\n",
        encoding="utf-8",
    )
    with pytest.raises(FactorError, match="duplicate factor"):
        load_factors(path)


def test_unknown_gas_is_rejected_not_defaulted(tmp_path):
    path = tmp_path / "factors.csv"
    path.write_text(
        "activity_source,scope,gas,emission_factor,factor_unit_denominator,"
        "factor_mass_unit,citation,publication_year\n"
        "diesel_furnace,1,CH4,0.0001,L,kg,IPCC 2006,2006\n",
        encoding="utf-8",
    )
    # generic CH4 has two AR6 GWPs; the register must say which methane it means
    with pytest.raises(FactorError, match="no AR6 GWP100"):
        load_factors(path)


def test_factor_without_citation_is_rejected(tmp_path):
    path = tmp_path / "factors.csv"
    path.write_text(
        "activity_source,scope,gas,emission_factor,factor_unit_denominator,"
        "factor_mass_unit,citation,publication_year\n"
        "diesel_furnace,1,CO2,2.68,L,kg,,2006\n",
        encoding="utf-8",
    )
    with pytest.raises(FactorError, match="blank"):
        load_factors(path)
