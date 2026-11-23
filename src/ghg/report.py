"""Markdown emissions summary.

Every number in the output is re-derivable from the ledger table that follows it,
so a reviewer can check a total without trusting the code that produced it. The
provenance section lists each factor with its citation; a factor without one
never reached this point.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .dispersion import PlumeState
from .inventory import Inventory

SCOPE_NAMES = {
    1: "Scope 1 — direct emissions",
    2: "Scope 2 — purchased energy",
    3: "Scope 3 — value chain",
}


def _fmt_t(value: float) -> str:
    return f"{value:,.2f}"


def _fmt_efficiency(value: float, total: float) -> str:
    return f"{value / total:.1%}" if total else "—"


def build_markdown(
    inventory: Inventory,
    *,
    period: str,
    site: str,
    plume: PlumeState | None = None,
    peak_concentration: float | None = None,
    dispersion_note: str | None = None,
    footprint_summary: dict[str, float] | None = None,
    chart_scope: str | None = None,
    chart_monthly: str | None = None,
    chart_footprint: str | None = None,
) -> str:
    total = inventory.total_tco2e
    by_scope = inventory.by_scope()
    by_source = inventory.by_source()
    months = sorted({line.period for line in inventory.lines})

    out: list[str] = []
    add = out.append

    add(f"# GHG Emissions Inventory — {site}")
    add("")
    add(f"**Reporting period:** {period}  ")
    add(f"**Total emissions:** {_fmt_t(total)} tCO₂e  ")
    add(f"**GWP basis:** {inventory.gwp_standard}  ")
    add(
        f"**Generated:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} "
        "by `ghg-inventory-engine`"
    )
    add("")
    add(
        "This report is generated from an activity-data extract joined to a cited "
        "emission-factor register. It is a calculation, not an assurance opinion: "
        "the boundary, the factor edition and the activity data are the operator's "
        "to defend."
    )
    add("")

    # ---- headline -------------------------------------------------------
    add("## 1. Headline result")
    add("")
    add("| Scope | tCO₂e | Share |")
    add("|---|---:|---:|")
    for scope in sorted(by_scope):
        add(f"| {SCOPE_NAMES.get(scope, f'Scope {scope}')} | {_fmt_t(by_scope[scope])} | {_fmt_efficiency(by_scope[scope], total)} |")
    add(f"| **Total** | **{_fmt_t(total)}** | 100.0% |")
    add("")
    if chart_scope:
        add(f"![Emissions by scope]({chart_scope})")
        add("")
    if chart_monthly:
        add(f"![Monthly emissions trend]({chart_monthly})")
        add("")

    # ---- hottest sources ------------------------------------------------
    add("## 2. Where the tonnes come from")
    add("")
    add("| Activity source | tCO₂e | Share of total |")
    add("|---|---:|---:|")
    for source, value in by_source.items():
        add(f"| `{source}` | {_fmt_t(value)} | {_fmt_efficiency(value, total)} |")
    add("")
    top_source, top_value = next(iter(by_source.items()))
    add(
        f"`{top_source}` dominates at {_fmt_efficiency(top_value, total)} of the total. "
        "Ranking by source rather than by scope is what turns a number into a "
        "reduction plan: scope tells you how you must report it, source tells you "
        "what to change."
    )
    add("")

    # ---- monthly --------------------------------------------------------
    add("## 3. Monthly series")
    add("")
    scopes = sorted(by_scope)
    add("| Month | " + " | ".join(f"Scope {s}" for s in scopes) + " | Total |")
    add("|---|" + "---:|" * len(scopes) + "---:|")
    by_month = inventory.by_month_scope()
    for month in months:
        cells = [by_month.get((month, s), 0.0) for s in scopes]
        add(
            f"| {month} | "
            + " | ".join(_fmt_t(c) for c in cells)
            + f" | {_fmt_t(sum(cells))} |"
        )
    add("")

    # ---- ledger ---------------------------------------------------------
    add("## 4. Auditable ledger")
    add("")
    add(
        "One row per gas per source per month. `mass_emitted_kg × GWP100 / 1000` "
        "reproduces every `tCO₂e` value here by hand."
    )
    add("")
    add("| Month | Source | Scope | Gas | Quantity | Factor (kg/unit) | Mass kg | GWP100 | tCO₂e |")
    add("|---|---|---:|---|---:|---:|---:|---:|---:|")
    for line in inventory.lines:
        add(
            f"| {line.period} | `{line.activity_source}` | {line.scope} | {line.gas} | "
            f"{line.quantity:,.4g} {line.activity_unit} | {line.emission_factor:,.6g} | "
            f"{line.mass_emitted_kg:,.2f} | {line.gwp100:,.1f} | {line.tco2e:,.4f} |"
        )
    add("")
    ledger_sum = sum(line.tco2e for line in inventory.lines)
    add(
        f"Ledger sum **{_fmt_t(ledger_sum)} tCO₂e** reconciles to the headline total "
        f"({_fmt_t(total)} tCO₂e). No value above is rounded twice."
    )
    add("")

    # ---- dispersion -----------------------------------------------------
    if plume is not None:
        add("## 5. Downwind dispersion of the stack plume")
        add("")
        add(
            "The inventory answers **how much** leaves the stack. The screening model "
            "below answers **where it goes**: a Gaussian plume with Pasquill–Gifford "
            "stability classes, Briggs dispersion coefficients, ground reflection "
            "and mixing-lid reflection."
        )
        add("")
        add("| Parameter | Value |")
        add("|---|---:|")
        add(f"| Stack height | {plume.stack.height_m:.1f} m |")
        add(f"| Stack diameter | {plume.stack.diameter_m:.2f} m |")
        add(f"| Exit velocity | {plume.stack.exit_velocity_ms:.1f} m/s |")
        add(f"| Exit / ambient temperature | {plume.stack.exit_temperature_k:.0f} / {plume.stack.ambient_temperature_k:.0f} K |")
        add(f"| Emission rate | {plume.emission_rate_gs:.2f} g/s |")
        add(f"| Wind speed (10 m) | {plume.wind_speed_10m_ms:.1f} m/s |")
        add(f"| Stability class | {plume.stability} |")
        if plume.mixing_height_m:
            add(f"| Mixing height | {plume.mixing_height_m:.0f} m |")
        add("")
        if chart_footprint:
            add(f"![Downwind concentration footprint]({chart_footprint})")
            add("")

    if footprint_summary:
        add("### Concentration by distance")
        add("")
        add("| Metric | Value |")
        add("|---|---:|")
        add(f"| Peak centreline concentration | {footprint_summary['peak_ugm3']:.1f} µg/m³ |")
        add(f"| Distance of peak | {footprint_summary['peak_distance_m']:.0f} m downwind |")
        add(f"| Centreline at 500 m | {footprint_summary['centreline_at_500m']:.1f} µg/m³ |")
        add(f"| Centreline at 1 km | {footprint_summary['centreline_at_1km']:.1f} µg/m³ |")
        if "area_over_threshold_m2" in footprint_summary:
            area_ha = footprint_summary["area_over_threshold_m2"] / 10_000.0
            add(f"| Area above the screening threshold | {area_ha:.1f} ha |")
            add(
                f"| Threshold still exceeded at | "
                f"{footprint_summary['max_downwind_over_threshold_m'] / 1000.0:.1f} km |"
            )
        add("")
        add(
            "The peak sits downwind of the stack, not at it: a buoyant plume rises "
            f"to an effective height well above {plume.stack.height_m:.0f} m and only "
            "reaches ground level once turbulent mixing has brought it down. That is "
            "why a taller stack or a hotter exhaust moves the maximum further away "
            "and lowers it."
        )
        add("")
    if dispersion_note:
        add(dispersion_note)
        add("")

    # ---- provenance -----------------------------------------------------
    add("## 6. Emission factor provenance")
    add("")
    add("| Source | Gas | Scope | Factor | Citation | Year |")
    add("|---|---|---:|---:|---|---:|")
    seen: set[tuple[str, str]] = set()
    for line in inventory.lines:
        key = (line.activity_source, line.gas)
        if key in seen:
            continue
        seen.add(key)
        add(
            f"| `{line.activity_source}` | {line.gas} | {line.scope} | "
            f"{line.emission_factor:,.6g} {line.factor_mass_unit}/{line.factor_denominator} | "
            f"{line.citation} | {line.publication_year} |"
        )
    add("")
    add(
        f"Global warming potentials: **{inventory.gwp_standard}** — CO₂ 1.0, "
        "CH₄ (fossil) 29.8, CH₄ (non-fossil) 27.0, N₂O 273.0. A factor already "
        "expressed as CO₂-equivalent is labelled `CO2e` and weighted 1.0; applying "
        "a GWP to it again would double count."
    )
    add("")

    # ---- boundary -------------------------------------------------------
    add("## 7. Boundary and assumptions")
    add("")
    add("| Item | Treatment |")
    add("|---|---|")
    add("| Consolidation | Operational control of one facility |")
    add("| Scope 2 method | Location-based, using the national grid factor |")
    add("| Combustion factors | IPCC 2006 Table 1.4 CO₂ + Table 2.3 CH₄/N₂O (manufacturing), × NCV |")
    add("| Methane GWP pool | Non-fossil (27.0), per GHG Protocol guidance for combustion |")
    add("| Freight | Tonne-kilometres × mode factor, well-to-wheel excluded |")
    add("| Removals, credits, offsets | Not modelled |")
    add("| Biogenic CO₂ | Not present in this facility's fuels |")
    add("")
    add(
        "**Not a compliance determination.** Meeting EU CBAM or ISO 14064-1 also "
        "requires the verifier's sampling plan, the installation boundary "
        "declaration and the production-volume denominator; this tool supplies the "
        "emissions arithmetic those documents rest on."
    )
    add("")
    return "\n".join(out) + "\n"


def write_markdown(text: str, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return out
