"""Plume footprint: the downwind concentration zone, as a map.

A single concentration at one receptor answers "is my neighbour over the limit".
A contour map answers "which neighbours are over it", which is the question a
permit application has to answer and the reason a dispersion module belongs
beside the carbon ledger at all.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .dispersion import PlumeState, centreline_concentration, ground_level_concentration


def plume_footprint(
    plume: PlumeState,
    path: str | Path,
    *,
    max_downwind_m: float = 3000.0,
    half_width_m: float = 1200.0,
    threshold_ugm3: float | None = None,
) -> tuple[Path, dict[str, float]]:
    """Contour map of ground-level concentration, µg/m³.

    The grid is denser near the source, where the gradient is steepest, and
    coarser far downwind where the field is smooth: a uniform grid either misses
    the near-field peak or wastes points at 3 km.

    Returns the written path and a small summary used by the CLI and report.
    """
    x = np.linspace(50.0, max_downwind_m, 160)
    y = np.linspace(-half_width_m, half_width_m, 200)

    # Vectorised directly rather than with a Python double loop: 32k cells at
    # ~30 µs each is a minute in a loop and milliseconds as arrays.
    from .dispersion import (
        briggs_sigmas,
        effective_stack_height_m,
        wind_at_height,
    )

    u = wind_at_height(
        plume.wind_speed_10m_ms, plume.stack.height_m, plume.stability, urban=plume.urban
    )
    h_eff = effective_stack_height_m(plume.stack, u, urban=plume.urban)

    sy = np.empty_like(x)
    sz = np.empty_like(x)
    for i, xi in enumerate(x):
        sy[i], sz[i] = briggs_sigmas(float(xi), plume.stability, urban=plume.urban)

    xx, yy = np.meshgrid(x, y, indexing="xy")
    syy = sy[None, :]
    szz = sz[None, :]

    prefactor = plume.emission_rate_gs / (2.0 * np.pi * u * syy * szz)
    crosswind = np.exp(-(yy**2) / (2.0 * syy**2))

    if plume.mixing_height_m is None:
        vertical = 2.0 * np.exp(-(h_eff**2) / (2.0 * szz**2))
    else:
        lid = plume.mixing_height_m
        vertical = np.zeros_like(szz)
        # Same series and same well-mixed switch as the scalar function; this
        # branch must stay in step with it or the map contradicts the number in
        # the report.
        well_mixed = szz > 1.6 * lid
        for n in range(-4, 5):
            vertical = vertical + np.exp(-((h_eff - 2.0 * n * lid) ** 2) / (2.0 * szz**2))
            vertical = vertical + np.exp(-((h_eff + 2.0 * n * lid) ** 2) / (2.0 * szz**2))
        vertical = np.where(well_mixed, np.sqrt(2.0 * np.pi) * szz / lid, vertical)

    field = prefactor * crosswind * vertical * 1e6  # µg/m³

    fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=160)
    peak = float(field.max())
    levels = np.linspace(0, peak, 14)[1:]

    filled = ax.contourf(xx, yy, field, levels=levels, cmap="YlOrRd", extend="max")
    ax.contour(xx, yy, field, levels=levels, colors="white", linewidths=0.4, alpha=0.5)

    if threshold_ugm3:
        line = ax.contour(
            xx, yy, field, levels=[threshold_ugm3], colors="#111827", linewidths=1.4
        )
        ax.clabel(line, fmt={threshold_ugm3: f"{threshold_ugm3:g} µg/m³"}, fontsize=7)

    # The stack itself, at the origin.
    ax.plot([0], [0], marker="^", color="#111827", markersize=8, label="stack")
    ax.annotate(
        f"{plume.stack.height_m:.0f} m stack\nH_eff = {h_eff:.0f} m",
        xy=(0, 0),
        xytext=(max_downwind_m * 0.03, half_width_m * 0.62),
        fontsize=7,
        color="#111827",
        arrowprops={"arrowstyle": "-", "color": "#6b7280", "lw": 0.7},
    )

    ax.set_xlabel("Downwind distance (m)")
    ax.set_ylabel("Crosswind offset (m)")
    ax.set_title(
        f"Ground-level concentration · stability {plume.stability} · "
        f"wind {plume.wind_speed_10m_ms:.1f} m/s · Q = {plume.emission_rate_gs:g} g/s",
        fontsize=8.5,
        loc="left",
    )
    ax.set_facecolor("#f7f5f2")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    bar = fig.colorbar(filled, ax=ax, pad=0.015)
    bar.set_label("µg/m³", fontsize=8)
    bar.ax.tick_params(labelsize=7)

    fig.tight_layout()
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out)
    plt.close(fig)

    # Peak location: the column with the highest centreline value. Using
    # field.argmax() gives the position of the single hottest cell, which is a
    # different question and drifts to a corner when the plume is flat.
    centreline = field[len(y) // 2, :]
    summary = {
        "peak_ugm3": float(centreline.max()),
        "peak_distance_m": float(x[int(centreline.argmax())]),
        "max_grid_ugm3": peak,
        # 500 m sits upstream of the peak here (~770 m); report both so the report
        # cannot imply the maximum is at the distance the user happened to ask for.
        "centreline_at_500m": centreline_concentration(plume, 500.0),
        "centreline_at_1km": centreline_concentration(plume, 1000.0),
    }
    if threshold_ugm3:
        over = field >= threshold_ugm3
        summary["area_over_threshold_m2"] = float(over.sum() * (x[1] - x[0]) * (y[1] - y[0]))
        summary["max_downwind_over_threshold_m"] = float(x[over.any(axis=0)].max()) if over.any() else 0.0
    return out, summary


def ground_level_at(plume: PlumeState, distance_m: float, y_m: float) -> float:
    """Re-export so callers do not import dispersion directly for one number."""
    return ground_level_concentration(plume, distance_m, y_m)
