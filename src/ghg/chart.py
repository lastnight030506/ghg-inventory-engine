"""Charts for the emissions report.

Two figures: scope breakdown and monthly trend. Both are written to PNG at a fixed
size so the PDF and the README show the same artifact.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: this runs inside a container
import matplotlib.pyplot as plt

from .inventory import Inventory

SCOPE_LABELS = {
    1: "Scope 1 — direct combustion",
    2: "Scope 2 — purchased electricity",
    3: "Scope 3 — value chain (inbound freight)",
}
SCOPE_COLOURS = {1: "#c0392b", 2: "#2471a3", 3: "#7f8c8d"}


def _style(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.25, linewidth=0.6)
    ax.set_axisbelow(True)


def scope_breakdown(inventory: Inventory, path: str | Path) -> Path:
    totals = inventory.by_scope()
    scopes = sorted(totals)
    values = [totals[s] for s in scopes]

    fig, ax = plt.subplots(figsize=(7.0, 3.4), dpi=160)
    bars = ax.barh(
        [SCOPE_LABELS.get(s, f"Scope {s}") for s in scopes],
        values,
        color=[SCOPE_COLOURS.get(s, "#555") for s in scopes],
        height=0.55,
    )
    total = sum(values) or 1.0
    for bar, value in zip(bars, values, strict=True):
        ax.text(
            bar.get_width() + total * 0.01,
            bar.get_y() + bar.get_height() / 2,
            f"{value:,.1f} t   ({value / total:.0%})",
            va="center",
            fontsize=8.5,
        )
    ax.set_xlabel("tCO₂e for the reporting year")
    ax.set_xlim(0, max(values) * 1.32 if values else 1)
    _style(ax)
    fig.tight_layout()
    out = Path(path)
    fig.savefig(out)
    plt.close(fig)
    return out


def monthly_trend(inventory: Inventory, path: str | Path) -> Path:
    months = sorted({line.period for line in inventory.lines})
    totals = inventory.by_month_scope()
    scopes = sorted({line.scope for line in inventory.lines})

    fig, ax = plt.subplots(figsize=(7.0, 3.2), dpi=160)
    bottom = [0.0] * len(months)
    for scope in scopes:
        series = [totals.get((month, scope), 0.0) for month in months]
        ax.bar(
            range(len(months)),
            series,
            bottom=bottom,
            color=SCOPE_COLOURS.get(scope, "#555"),
            label=f"Scope {scope}",
            width=0.72,
        )
        bottom = [b + s for b, s in zip(bottom, series, strict=True)]

    ax.set_xticks(range(len(months)))
    ax.set_xticklabels([m[5:] for m in months], fontsize=8)
    ax.set_xlabel("Month of 2025")
    ax.set_ylabel("tCO₂e")
    ax.legend(frameon=False, fontsize=7.5, ncol=len(scopes))
    _style(ax)
    fig.tight_layout()
    out = Path(path)
    fig.savefig(out)
    plt.close(fig)
    return out
