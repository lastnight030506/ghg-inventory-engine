"""Gaussian plume: hand-checkable physics.

Every test compares the code against arithmetic worked by hand from the governing
equation, not against a stored expected value the code produced. The point is
that a reviewer can redo the sum.
"""

from __future__ import annotations

import math

import pytest

from ghg.dispersion import (
    PlumeState,
    Stack,
    briggs_sigmas,
    centreline_concentration,
    effective_stack_height_m,
    ground_level_concentration,
    peak_downwind_distance,
    plume_rise_m,
    screening_confidence,
    stability_from_weather,
    stack_tip_downwash_m,
    wind_at_height,
)


@pytest.fixture
def stack():
    return Stack(
        height_m=30.0,
        diameter_m=2.0,
        exit_velocity_ms=12.0,
        exit_temperature_k=400.0,
        ambient_temperature_k=293.0,
    )


@pytest.fixture
def plume(stack):
    return PlumeState(
        stack=stack, emission_rate_gs=25.0, wind_speed_10m_ms=3.0, stability="D"
    )


# ---------------------------------------------------------------- geometry


def test_stack_area_and_flow(stack):
    """d=2.0 -> r=1.0 -> area = pi = 3.1416 m2. 12 m/s x pi = 37.7 m3/s."""
    assert stack.area_m2 == pytest.approx(math.pi)
    assert stack.volumetric_flow_m3s == pytest.approx(12.0 * math.pi)


def test_wind_profile_increases_with_height():
    """u(z) = u10*(z/10)^p. Rural D uses p=0.15, not 0.25: 3*(3)^0.15 = 3.537.

    The rural and urban exponent sets differ substantially (rural F is 0.55,
    urban F is 0.30), and concentration is inversely proportional to u, so using
    the urban set on a rural site biases every stable-air result.
    """
    assert wind_at_height(3.0, 30.0, "D") == pytest.approx(3.0 * 3.0**0.15)
    assert wind_at_height(3.0, 10.0, "D") == pytest.approx(3.0)
    # the urban column is the one with p=0.25 for D
    assert wind_at_height(3.0, 30.0, "D", urban=True) == pytest.approx(3.0 * 3.0**0.25)
    assert wind_at_height(3.0, 30.0, "D", urban=True) > wind_at_height(3.0, 30.0, "D")


def test_rural_and_urban_wind_exponents_differ_most_in_stable_air():
    """Rural F (0.55) is far steeper than urban F (0.30): a stable rural
    boundary layer decouples the stack from the surface anemometer."""
    rural_f = wind_at_height(2.0, 60.0, "F")
    urban_f = wind_at_height(2.0, 60.0, "F", urban=True)
    assert rural_f > urban_f


def test_wind_profile_is_steeper_in_stable_air():
    unstable = wind_at_height(3.0, 100.0, "A")
    stable = wind_at_height(3.0, 100.0, "F")
    assert stable > unstable


# ---------------------------------------------------------------- plume rise


def test_holland_plume_rise_by_hand(stack):
    """Holland, with no downwash because vs clears 1.5u.

    1.5*u = 5.31 m/s, vs = 12 m/s, so h' = h.
    u         = 3*(30/10)^0.15             = 3.5374 m/s
    momentum  = 12*2.0/3.5374              = 6.7846
    buoyancy  = 2.68e-3*1013*2.0*(107/400) = 1.4524
    dh        = 6.7846*(1.5+1.4524)        = 20.031 m
    """
    u = wind_at_height(3.0, 30.0, "D")
    assert u == pytest.approx(3.5374, abs=1e-4)
    expected = (12.0 * 2.0 / u) * (1.5 + 2.68e-3 * 1013.0 * 2.0 * 107.0 / 400.0)
    assert plume_rise_m(stack, u) == pytest.approx(expected)
    assert plume_rise_m(stack, u) == pytest.approx(20.03, abs=0.01)


def test_downwash_correction_lowers_the_stack_for_a_lazy_plume():
    """Briggs (1973): h' = h + 2[(vs/u) - 1.5]d, applied only when vs < 1.5u.

    2 m/s exit in 5 m/s wind, 1 m diameter:
        ratio  = 2/5 = 0.4
        h'     = 20 + 2*(0.4-1.5)*1.0 = 20 - 2.2 = 17.8 m

    The correction LOWERS the release height. An earlier version raised the exit
    velocity instead, which credited a lazy plume with momentum it does not have
    and under-predicted ground-level concentration. This test pins the direction.
    """
    lazy = Stack(
        height_m=20.0, diameter_m=1.0, exit_velocity_ms=2.0,
        exit_temperature_k=350.0, ambient_temperature_k=293.0,
    )
    assert stack_tip_downwash_m(lazy, 5.0) == pytest.approx(-2.2)
    uncorrected_h_eff = 20.0 + plume_rise_m(lazy, 5.0)
    assert effective_stack_height_m(lazy, 5.0) < uncorrected_h_eff


def test_downwash_is_zero_when_exit_velocity_is_high():
    """vs >= 1.5u needs no correction: the jet outruns its own wake."""
    fast = Stack(30.0, 2.0, 12.0, 400.0, 293.0)
    # 1.5u = 5.92 m/s, and vs = 12 m/s clears it
    assert stack_tip_downwash_m(fast, 3.948) == 0.0
    assert effective_stack_height_m(fast, 3.948) == pytest.approx(
        30.0 + plume_rise_m(fast, 3.948)
    )


def test_downwash_cannot_drive_the_plume_underground():
    """A very wide stack with a slow jet would give a negative h'; it is floored."""
    absurd = Stack(
        height_m=2.0, diameter_m=8.0, exit_velocity_ms=0.1,
        exit_temperature_k=300.0, ambient_temperature_k=293.0,
    )
    assert effective_stack_height_m(absurd, 10.0) >= 1.0


def test_effective_height_is_physical_plus_rise(stack):
    u = wind_at_height(3.0, 30.0, "D")
    assert effective_stack_height_m(stack, u) == pytest.approx(30.0 + plume_rise_m(stack, u))


# ---------------------------------------------------------------- sigmas


def test_briggs_sigma_is_a_factor_of_x_in_neutral_air():
    """Class D open country at x = 1000 m. This pins both b coefficients, which a
    copied-from-memory table routinely gets wrong: sigma_z uses b=0.0015, not the
    0.0001 used for sigma_y.

    sigma_y = 0.08*1000*(1+0.1)^-0.5   = 76.28 m
    sigma_z = 0.06*1000*(1+1.5)^-0.5   = 37.95 m
    """
    sy, sz = briggs_sigmas(1000.0, "D")
    assert sy == pytest.approx(80.0 * 1.1**-0.5)
    assert sz == pytest.approx(60.0 * 2.5**-0.5)
    assert (sy, sz) == pytest.approx((76.28, 37.95), abs=0.02)


def test_sigma_ordering_across_stability():
    """Unstable air spreads faster than stable air at every distance."""
    distances = (100, 500, 2000)
    for x in distances:
        sy_a, _ = briggs_sigmas(x, "A")
        sy_f, _ = briggs_sigmas(x, "F")
        assert sy_a > sy_f, f"sigma_y at {x} m"


def test_urban_coefficient_tables_differ_from_rural_per_class():
    """Pins the urban sigma_z coefficient for E/F: b = 0.00015, not 0.0015.

    A 10x error here is invisible at short range and wrong at 2 km, which is
    exactly where a fence-line receptor sits. Values from the Briggs table as
    reproduced in the standard references.
    """
    # urban E: sigma_z = 0.08*x*(1+0.00015*x)^-0.5 -> at x=2000: 0.08*2000*(1.3)^-0.5
    _, sz_urban_e = briggs_sigmas(2000.0, "E", urban=True)
    assert sz_urban_e == pytest.approx(160.0 * 1.3**-0.5)
    # a 0.0015 b coefficient would give 160*(1+3)^-0.5 = 80 m instead
    assert sz_urban_e == pytest.approx(140.3, abs=0.2)


def test_sigma_grows_with_distance():
    sy1, sz1 = briggs_sigmas(100.0, "D")
    sy2, sz2 = briggs_sigmas(1000.0, "D")
    assert sy2 > sy1 and sz2 > sz1


def test_urban_spreads_faster_than_rural():
    rural_y, _ = briggs_sigmas(500.0, "D", urban=False)
    urban_y, _ = briggs_sigmas(500.0, "D", urban=True)
    assert urban_y > rural_y


def test_confidence_flags_extrapolation():
    assert screening_confidence(500) == "within fitted range"
    assert "below" in screening_confidence(50)
    assert "beyond" in screening_confidence(20_000)


# ---------------------------------------------------------------- concentration


def test_centreline_concentration_by_hand(plume):
    """Full hand calculation at x = 500 m, y = 0, no lid.

    u    = 3*(30/10)^0.15                 = 3.5374 m/s
    dh   = 20.031 m  ->  H_eff = 50.031 m   (no downwash: 12 > 1.5*3.5374)
    sy   = 0.08*500*(1+0.05)^-0.5         = 39.036 m
    sz   = 0.06*500*(1+0.75)^-0.5         = 22.678 m
    pre  = 25/(2*pi*3.5374*39.036*22.678) = 1.2706e-3 g/m3
    vert = 2*exp(-50.031^2/(2*22.678^2))  = 2*exp(-2.4339) = 0.1754
    C    = 1.2706e-3*0.1754*1e6           = 222.9 ug/m3
    """
    u = wind_at_height(3.0, 30.0, "D")
    heff = effective_stack_height_m(plume.stack, u)
    sy, sz = briggs_sigmas(500.0, "D")
    expected = (
        25.0 / (2 * math.pi * u * sy * sz)
        * 2 * math.exp(-(heff**2) / (2 * sz**2))
        * 1e6
    )
    assert centreline_concentration(plume, 500.0) == pytest.approx(expected)
    assert centreline_concentration(plume, 500.0) == pytest.approx(222.9, abs=0.1)


def test_concentration_scales_linearly_with_emission_rate(plume):
    doubled = PlumeState(
        stack=plume.stack,
        emission_rate_gs=plume.emission_rate_gs * 2,
        wind_speed_10m_ms=plume.wind_speed_10m_ms,
        stability=plume.stability,
    )
    assert centreline_concentration(doubled, 500.0) == pytest.approx(
        2 * centreline_concentration(plume, 500.0)
    )


def test_concentration_falls_with_distance_from_the_peak(plume):
    peak_x = peak_downwind_distance(plume)
    assert centreline_concentration(plume, peak_x) > centreline_concentration(plume, 5000.0)


def test_peak_is_a_local_maximum(plume):
    peak_x = peak_downwind_distance(plume)
    peak = centreline_concentration(plume, peak_x)
    for x in (peak_x - 50, peak_x + 50):
        if x > 0:
            assert centreline_concentration(plume, x) <= peak


def test_crosswind_decay_is_symmetric(plume):
    left = ground_level_concentration(plume, 500.0, -100.0)
    right = ground_level_concentration(plume, 500.0, 100.0)
    centre = ground_level_concentration(plume, 500.0, 0.0)
    assert left == pytest.approx(right)
    assert centre > left


def test_steady_stable_air_concentrates_more_downwind(plume):
    """Same emission, same wind at 10 m: stable air keeps it together longer.

    This is the physical reason a night-time inversion is a permitting problem,
    and the test fails if sigma_z is ever wired to the wrong class.
    """
    stable = PlumeState(
        stack=plume.stack, emission_rate_gs=25.0, wind_speed_10m_ms=3.0, stability="F"
    )
    unstable = PlumeState(
        stack=plume.stack, emission_rate_gs=25.0, wind_speed_10m_ms=3.0, stability="A"
    )
    assert centreline_concentration(stable, 1000.0) != centreline_concentration(unstable, 1000.0)


def test_mixing_lid_stops_the_far_field_from_decaying_away(plume):
    """A lid traps the plume in a shallow layer, so beyond the lid's reach the
    concentration levels off instead of decaying to nothing the way an uncapped
    plume does. Compare the decay ratio from 15 km to 30 km.
    """
    capped = PlumeState(
        stack=plume.stack,
        emission_rate_gs=25.0,
        wind_speed_10m_ms=3.0,
        stability="D",
        mixing_height_m=300.0,
    )
    open_ratio = centreline_concentration(plume, 30_000.0) / centreline_concentration(plume, 15_000.0)
    capped_ratio = centreline_concentration(capped, 30_000.0) / centreline_concentration(capped, 15_000.0)
    assert capped_ratio > open_ratio, "capped plume should decay more slowly"


def test_well_mixed_limit_is_used_when_sigma_exceeds_the_lid(plume):
    """sigma_z > 1.6L: the series is replaced by the uniform-mixing limit.

    C = Q/(sqrt(2pi) u sy L). Checked against that expression directly.
    """
    capped = PlumeState(
        stack=plume.stack, emission_rate_gs=25.0, wind_speed_10m_ms=3.0,
        stability="D", mixing_height_m=100.0,
    )
    x = 50_000.0
    u = wind_at_height(3.0, 30.0, "D")
    sy, sz = briggs_sigmas(x, "D")
    assert sz > 1.6 * 100.0, "test premise: needs a well-mixed sigma_z"
    expected = 25.0 / (math.sqrt(2 * math.pi) * u * sy * 100.0) * 1e6
    assert centreline_concentration(capped, x) == pytest.approx(expected, rel=1e-6)


def test_mixing_height_below_stack_top_is_rejected(plume):
    with pytest.raises(ValueError, match="above the physical stack top"):
        PlumeState(
            stack=plume.stack, emission_rate_gs=25.0, wind_speed_10m_ms=3.0,
            stability="D", mixing_height_m=20.0,
        )


def test_invalid_inputs_raise_rather_than_return_garbage():
    stack = Stack(30.0, 2.0, 12.0, 400.0, 293.0)
    with pytest.raises(ValueError, match="stability"):
        PlumeState(stack=stack, emission_rate_gs=1.0, wind_speed_10m_ms=3.0, stability="G")
    with pytest.raises(ValueError, match="wind"):
        PlumeState(stack=stack, emission_rate_gs=1.0, wind_speed_10m_ms=0.0, stability="D")
    with pytest.raises(ValueError, match="distance"):
        briggs_sigmas(0.0, "D")
    with pytest.raises(ValueError, match="height_m must be positive"):
        Stack(0.0, 2.0, 12.0, 400.0, 293.0)


# ---------------------------------------------------------------- stability


def test_stability_table_daytime():
    assert stability_from_weather(1.0, insolation="strong") == "A"
    assert stability_from_weather(1.0, insolation="slight") == "B"
    assert stability_from_weather(10.0, insolation="slight") == "D"


def test_stability_table_night_uses_cloud_cover():
    """Clear nights are more stable than cloudy nights: less mixing."""
    clear = stability_from_weather(1.0, night_cloud_eighths=0)
    cloudy = stability_from_weather(1.0, night_cloud_eighths=8)
    assert clear == "F"
    assert cloudy == "F" or cloudy in ("E", "F")


def test_stability_needs_weather_context():
    with pytest.raises(ValueError, match="insolation or night cloud"):
        stability_from_weather(3.0)
