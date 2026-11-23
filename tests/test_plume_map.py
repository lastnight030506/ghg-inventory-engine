"""Plume footprint map: the vectorised field must agree with the scalar model.

The map is a second implementation of the same physics in numpy. If the two
drift, the report shows a number that contradicts its own picture — so the tests
compare them cell by cell rather than eyeballing the image.
"""

from __future__ import annotations

import pytest

from ghg.dispersion import (
    PlumeState,
    Stack,
    centreline_concentration,
    peak_downwind_distance,
)
from ghg.plume_map import plume_footprint


@pytest.fixture
def stack():
    return Stack(30.0, 2.0, 12.0, 400.0, 293.0)


@pytest.fixture
def plume(stack):
    return PlumeState(stack=stack, emission_rate_gs=25.0, wind_speed_10m_ms=3.0, stability="D")


def test_map_is_written_and_non_trivial(tmp_path, plume):
    path, summary = plume_footprint(plume, tmp_path / "foot.png")
    assert path.exists()
    assert path.stat().st_size > 20_000
    assert summary["peak_ugm3"] > 0


def test_map_summary_matches_the_scalar_model(tmp_path, plume):
    """The contour map and `centreline_concentration` must agree to plotting
    precision at the same distances."""
    _, summary = plume_footprint(plume, tmp_path / "f.png")
    assert summary["centreline_at_500m"] == pytest.approx(centreline_concentration(plume, 500.0), rel=0.02)
    assert summary["centreline_at_1km"] == pytest.approx(centreline_concentration(plume, 1000.0), rel=0.02)


def test_map_peak_is_near_the_scanned_peak(tmp_path, plume):
    """Grid resolution is 160 columns over 3 km, so the map's peak position agrees
    with a 5 m scan only to within one cell (~19 m)."""
    _, summary = plume_footprint(plume, tmp_path / "f.png")
    assert summary["peak_distance_m"] == pytest.approx(peak_downwind_distance(plume), abs=40)
    at_peak = centreline_concentration(plume, summary["peak_distance_m"])
    assert summary["peak_ugm3"] == pytest.approx(at_peak, rel=0.03)


def test_mixing_lid_map_agrees_with_scalar_model(tmp_path, plume):
    """The well-mixed branch is written twice (scalar and array). This is the test
    that catches them diverging."""
    capped = PlumeState(
        stack=plume.stack,
        emission_rate_gs=25.0,
        wind_speed_10m_ms=3.0,
        stability="D",
        mixing_height_m=300.0,
    )
    _, summary = plume_footprint(capped, tmp_path / "c.png", max_downwind_m=4000.0)
    assert summary["centreline_at_1km"] == pytest.approx(
        centreline_concentration(capped, 1000.0), rel=0.02
    )


def test_threshold_area_is_reported_when_a_threshold_is_given(tmp_path, plume):
    _, summary = plume_footprint(plume, tmp_path / "t.png", threshold_ugm3=50.0)
    assert summary["area_over_threshold_m2"] > 0
    assert summary["max_downwind_over_threshold_m"] > 0


def test_higher_emission_produces_a_larger_threshold_area(tmp_path, plume):
    """Sanity: more pollutant, bigger exceedance footprint. Linear scaling means
    the area is not simply double, but it must increase."""
    doubled = PlumeState(
        stack=plume.stack, emission_rate_gs=50.0, wind_speed_10m_ms=3.0, stability="D"
    )
    _, small = plume_footprint(plume, tmp_path / "a.png", threshold_ugm3=100.0)
    _, large = plume_footprint(doubled, tmp_path / "b.png", threshold_ugm3=100.0)
    assert large["area_over_threshold_m2"] > small["area_over_threshold_m2"]
