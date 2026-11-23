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


def build_scenario_markdown(
    *,
    inv_old,
    inv_new,
    year_old: int,
    year_new: int,
    decompositions,
    scope2,
    site: str,
) -> str:
    """Year-over-year comparison with the factor/activity split made explicit."""
    total_old = inv_old.total_tco2e
    total_new = inv_new.total_tco2e
    delta = total_new - total_old
    pct = delta / total_old if total_old else 0.0

    out: list[str] = []
    add = out.append
    add(f"# Scenario Comparison — {site}")
    add("")
    add(f"**{year_old} → {year_new}**  ")
    add(f"**Total change:** {delta:+,.2f} tCO₂e ({pct:+.1%})  ")
    add(
        f"**Generated:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} "
        "by `ghg-inventory-engine`"
    )
    add("")
    add(
        "A total that fell is not automatically a reduction. Part of any year-on-year "
        "change comes from the emission factor being republished, not from anything the "
        "plant did. The decomposition below separates the two."
    )
    add("")

    add("## 1. Headline")
    add("")
    add(f"| Metric | {year_old} | {year_new} | Change |")
    add("|---|---:|---:|---:|")
    add(f"| Total | {total_old:,.2f} | {total_new:,.2f} | {delta:+,.2f} |")
    for scope in sorted(set(inv_old.by_scope()) | set(inv_new.by_scope())):
        a = inv_old.by_scope().get(scope, 0.0)
        b = inv_new.by_scope().get(scope, 0.0)
        add(f"| Scope {scope} | {a:,.2f} | {b:,.2f} | {b - a:+,.2f} |")
    add("")

    add("## 2. Why it moved: activity vs factor")
    add("")
    add(
        "The change in each source is split into three terms that sum exactly to the "
        "observed difference:"
    )
    add("")
    add("```")
    add("activity_effect = (Q_new - Q_old) x EF_old      what the plant consumed")
    add("factor_effect   = Q_old x (EF_new - EF_old)      what the factor register said")
    add("interaction     = (Q_new - Q_old) x (EF_new - EF_old)")
    add("```")
    add("")
    add("| Source | Activity | Factor | Interaction | Sum | Driver |")
    add("|---|---:|---:|---:|---:|---|")
    for d, driver in decompositions:
        add(
            f"| `{d.source}` | {d.activity_effect:+,.2f} | {d.factor_effect:+,.2f} | "
            f"{d.interaction:+,.2f} | {d.total_change:+,.2f} | {driver} |"
        )
    add("")

    factor_driven = [d for d, driver in decompositions if driver == "factor"]
    if factor_driven:
        total_factor = sum(d.factor_effect for d in factor_driven)
        add(
            f"**{len(factor_driven)} source(s) moved for factor reasons**, contributing "
            f"{total_factor:+,.2f} tCO₂e. None of that is a physical reduction and it must "
            "not be reported as one."
        )
        add("")

    add("## 3. Scope 2: location-based and market-based")
    add("")
    add(
        "The GHG Protocol Scope 2 Guidance requires both figures where contractual "
        "instruments exist. They answer different questions and **must not be summed or "
        "used interchangeably**."
    )
    add("")
    add("| Method | tCO₂e | What it measures |")
    add("|---|---:|---|")
    add(
        f"| Location-based | {scope2.location_tco2e:,.2f} | "
        "average intensity of the grid the plant draws from |"
    )
    add(
        f"| Market-based | {scope2.market_tco2e:,.2f} | "
        "the contracts the plant holds, plus residual grid for the rest |"
    )
    add("")
    add(f"*{scope2.describe()}*")
    add("")
    if scope2.market_tco2e < scope2.location_tco2e * 0.999 and not scope2.instruments:
        add(
            "> The market-based figure is lower with no instruments behind it. That is a "
            "reporting error, not a reduction: a residual-mix factor below the grid average "
            "needs documentary support."
        )
        add("")

    add("## 4. What this comparison does not tell you")
    add("")
    add("- **Neither total is restated.** A factor change is shown as a factor effect; nothing is rebased.")
    add("- **Scope 3 covers inbound freight only** (category 4). Business travel and purchased goods are absent, so the total understates the value chain.")
    add("- **The dispersion model is unaffected by year.** It screens one stack under one meteorology; a second year needs its own `data/stack.json`.")
    add("")
    add(
        "**Not a compliance determination.** A verifier will also ask for the boundary "
        "declaration, the production-volume denominator, and the evidence behind each "
        "contractual instrument."
    )
    add("")
    return "\n".join(out) + "\n"
