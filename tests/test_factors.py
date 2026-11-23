"""The shipped factor register.

These tests guard the numbers that end up in a filing. They do not re-derive
IPCC's tables; they check the register is internally consistent and that the
derived per-unit values are the right order of magnitude, which is what catches a
grams/kilograms slip — a 1000x error that still looks like a number.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ghg.factors import GWP100_AR6, load_factors

REGISTER = Path(__file__).resolve().parents[1] / "data" / "factors" / "emission_factors.csv"


@pytest.fixture(scope="module")
def register():
    return load_factors(REGISTER)


def _by(register, source, gas):
    for factor in register[source]:
        if factor.gas == gas:
            return factor
    raise AssertionError(f"{source}/{gas} missing from the register")


def test_every_row_has_a_citation_and_a_plausible_year(register):
    for source, factors in register.items():
        for factor in factors:
            assert factor.citation.strip(), f"{source}/{factor.gas} has no citation"
            assert 1990 <= factor.publication_year <= 2026
            assert factor.gas in GWP100_AR6


def test_combustion_methane_uses_the_non_fossil_gwp(register):
    """GHG Protocol's GWP guidance assigns non-fossil CH4 (27.0) to stationary
    combustion; the fossil value (29.8) belongs to fugitive fossil sources. Using
    the wrong one overstates combustion methane by 10%."""
    for source in ("diesel_furnace", "coal_boiler"):
        gases = {f.gas for f in register[source]}
        assert "CH4_non_fossil" in gases, f"{source} should classify its methane"
        assert "CH4_fossil" not in gases, f"{source} is combustion, not fugitive"


def test_every_source_in_the_activity_file_has_factors(register):
    """The register and the activity extract must not drift apart."""
    import csv

    activity = REGISTER.parents[1] / "activity" / "activity_2025.csv"
    with activity.open(newline="", encoding="utf-8") as handle:
        sources = {row["activity_source"] for row in csv.DictReader(handle)}
    assert sources == set(register), (
        f"activity sources {sorted(sources)} != register sources {sorted(register)}"
    )


def test_diesel_co2_is_about_2_7_kg_per_litre(register):
    """Diesel is ~2.6-2.7 kg CO2/L. Outside that band something is off by 10x."""
    factor = _by(register, "diesel_furnace", "CO2")
    assert 2.5 < factor.emission_factor < 2.8


def test_diesel_ch4_and_n2o_are_trace_levels(register):
    """CH4 and N2O from diesel are fractions of a gram per litre, not kilos.

    Table 2.3 (manufacturing) gives 10 kg CH4/TJ, not Table 2.2's 3 kg/TJ: a
    factory furnace is not a power station and the two tables are not
    interchangeable.
    """
    ch4 = next(f for f in register["diesel_furnace"] if f.gas.startswith("CH4"))
    n2o = next(f for f in register["diesel_furnace"] if f.gas == "N2O")
    assert ch4.emission_factor < 0.01
    assert n2o.emission_factor < 0.01
    # 10 kg CH4/TJ * 43 TJ/Gg * 0.84 kg/L = 361 g/L = 0.361 g/L
    assert ch4.emission_factor == pytest.approx(0.000361, abs=1e-6)


def test_coal_co2_is_about_2_4_kg_per_kg(register):
    """Factor is kg CO2 per tonne of coal (activity unit is t): ~2440 kg/t, i.e.
    2.44 kg CO2 per kg of coal."""
    factor = _by(register, "coal_boiler", "CO2")
    assert factor.denominator == "t"
    assert 2200 < factor.emission_factor < 2700
    assert 2.2 < factor.emission_factor / 1000 < 2.7


def test_coal_trace_gases_are_grams_not_kilograms(register):
    """The bug this pins: 25.8 kg CH4 per tonne of coal is 1000x the real value.

    Table 2.3: 10 kg CH4/TJ * 25.8 TJ/Gg = 258 g/t = 0.258 kg/t.
    """
    ch4 = _by(register, "coal_boiler", "CH4_non_fossil")
    n2o = _by(register, "coal_boiler", "N2O")
    assert ch4.emission_factor == pytest.approx(0.258, abs=1e-6)
    assert n2o.emission_factor == pytest.approx(0.0387, abs=1e-6)
    assert ch4.tco2e(1.0) < 0.01  # one tonne of coal: a few kg CO2e of CH4


def test_vietnam_grid_factor_matches_the_published_series(register):
    """The official Vietnamese series runs 0.9130 (2018) down to 0.6187 (2024).

    The register uses the 2024 figure because it is the latest official one. The
    test pins the published series rather than just a plausible range, so a
    mistyped digit or a factor-of-10 unit slip fails.
    """
    factor = _by(register, "grid_electricity", "CO2e")
    official_series = {0.9130, 0.8649, 0.8458, 0.8041, 0.7221, 0.6766, 0.6592, 0.6187}
    assert factor.scope == 2
    assert factor.emission_factor in official_series, (
        f"{factor.emission_factor} is not one of the published Vietnam grid factors"
    )
    assert factor.publication_year == 2024
    # 0.6187 kg/kWh == 0.6187 tCO2/MWh, so 1 MWh of activity yields 0.6187 tCO2e
    assert factor.tco2e(1000.0) == pytest.approx(0.6187, abs=1e-4)


def test_freight_factors_are_per_tonne_km_and_ordered(register):
    """Road freight per tonne-km is several times sea freight, never the reverse."""
    road = _by(register, "inbound_freight_road", "CO2e")
    sea = _by(register, "inbound_freight_sea", "CO2e")
    assert road.denominator == "tkm" and sea.denominator == "tkm"
    assert road.emission_factor > sea.emission_factor
    assert 0.05 < road.emission_factor < 0.2
    assert 0.005 < sea.emission_factor < 0.05


def test_trace_gases_never_dominate_the_total(register):
    """CO2 must dominate combustion. If CH4 outweighed it, a GWP or unit is wrong."""
    for source in ("diesel_furnace", "coal_boiler"):
        co2 = _by(register, source, "CO2").tco2e(1000.0)
        others = sum(
            f.tco2e(1000.0) for f in register[source] if f.gas != "CO2"
        )
        assert others < co2, f"{source}: trace gases exceed CO2"


def test_scope_assignment_matches_the_boundary(register):
    assert all(f.scope == 2 for f in register["grid_electricity"])
    assert all(f.scope == 1 for f in register["diesel_furnace"])
    assert all(f.scope == 1 for f in register["coal_boiler"])
    assert all(f.scope == 3 for f in register["inbound_freight_road"])
    assert all(f.scope == 3 for f in register["inbound_freight_sea"])
