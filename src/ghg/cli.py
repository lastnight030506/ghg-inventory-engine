"""Command line entry point.

    ghg inventory   -> calculate, chart, write Markdown + PDF
    ghg dispersion  -> evaluate the plume at receptor points
    ghg factors     -> print the factor register with citations

Exit codes: 0 success, 1 calculation/input failure, 2 usage error. A scheduler
branches on the code, not on log text.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .activity import ActivityError, load_activity
from .dispersion import PlumeState, Stack, concentration_grid
from .factors import FactorError, load_factors
from .inventory import build_inventory
from .plume_map import plume_footprint
from .report import build_markdown, write_markdown

DEFAULT_ACTIVITY = "data/activity/activity_2025.csv"
DEFAULT_FACTORS = "data/factors/emission_factors.csv"
DEFAULT_OUT = "out"


def _run_inventory(args: argparse.Namespace) -> int:
    from .chart import monthly_trend, scope_breakdown
    from .pdf import markdown_to_pdf

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    records = load_activity(args.activity)
    register = load_factors(args.factors)
    inventory = build_inventory(records, register)

    # Charts and the report live together; the Markdown references the PNGs by
    # relative name so the same file renders in the repo and in the PDF.
    scope_png = scope_breakdown(inventory, out / "scope_breakdown.png")
    month_png = monthly_trend(inventory, out / "monthly_trend.png")

    plume = None
    peak = None
    note = None
    footprint_summary = None
    footprint_png = None
    if args.stack_config:
        plume = _plume_from_config(Path(args.stack_config))
        footprint_png, footprint_summary = plume_footprint(
            plume, out / "plume_footprint.png", max_downwind_m=args.footprint_km * 1000.0
        )
        peak = footprint_summary["peak_ugm3"]
        note = (
            f"Peak ground-level concentration **{footprint_summary['peak_ugm3']:.1f} µg/m³** at "
            f"**{footprint_summary['peak_distance_m']:.0f} m** downwind on the plume centreline, "
            f"stability {plume.stability}, wind {plume.wind_speed_10m_ms:.1f} m/s. "
            f"At 500 m the centreline value is {footprint_summary['centreline_at_500m']:.1f} µg/m³. "
            "Screening estimate only — see `ghg/dispersion.py` for model limits."
        )

    text = build_markdown(
        inventory,
        period=f"{min(r.period for r in records)} to {max(r.period for r in records)}",
        site=records[0].site,
        plume=plume,
        peak_concentration=peak,
        dispersion_note=note,
        footprint_summary=footprint_summary,
        chart_scope=scope_png.name,
        chart_monthly=month_png.name,
        chart_footprint=footprint_png.name if footprint_png else None,
    )
    md_path = write_markdown(text, out / "emissions_report.md")
    pdf_path = markdown_to_pdf(text, out / "emissions_report.pdf", base_dir=out)

    totals = inventory.by_scope()
    print(f"inventory: {len(inventory.lines)} lines, {len(records)} activity rows")
    for scope, value in totals.items():
        print(f"  scope {scope}: {value:,.2f} tCO2e")
    print(f"  total: {inventory.total_tco2e:,.2f} tCO2e")
    if footprint_summary:
        print(
            f"dispersion: peak {footprint_summary['peak_ugm3']:.1f} ug/m3 at "
            f"{footprint_summary['peak_distance_m']:.0f} m"
        )
    print(f"markdown: {md_path}")
    print(f"pdf: {pdf_path}")
    return 0


def _plume_from_config(path: Path) -> PlumeState:
    config = json.loads(path.read_text(encoding="utf-8"))
    return PlumeState(
        stack=Stack(
            height_m=config["height_m"],
            diameter_m=config["diameter_m"],
            exit_velocity_ms=config["exit_velocity_ms"],
            exit_temperature_k=config["exit_temperature_k"],
            ambient_temperature_k=config["ambient_temperature_k"],
        ),
        emission_rate_gs=config["emission_rate_gs"],
        wind_speed_10m_ms=config["wind_speed_10m_ms"],
        stability=config["stability"],
        mixing_height_m=config.get("mixing_height_m"),
    )


def _run_dispersion(args: argparse.Namespace) -> int:
    stack = Stack(
        height_m=args.height,
        diameter_m=args.diameter,
        exit_velocity_ms=args.velocity,
        exit_temperature_k=args.exit_temp,
        ambient_temperature_k=args.ambient_temp,
    )
    plume = PlumeState(
        stack=stack,
        emission_rate_gs=args.emission,
        wind_speed_10m_ms=args.wind,
        stability=args.stability,
        mixing_height_m=args.mixing_height,
    )
    grid = concentration_grid(
        plume, distances_m=tuple(args.distance), y_m=0.0
    )
    print(f"{'x (m)':>10} {'y (m)':>8} {'ug/m3':>12}")
    for x, y, value in grid:
        print(f"{x:>10.1f} {y:>8.1f} {value:>12.3f}")
    return 0


def _show_factors(args: argparse.Namespace) -> int:
    register = load_factors(args.factors)
    for source, factors in sorted(register.items()):
        print(f"{source}")
        for factor in factors:
            print(
                f"  scope {factor.scope}  {factor.gas:<12} "
                f"{factor.emission_factor:>10.6g} {factor.mass_unit}/{factor.denominator}"
                f"   [{factor.publication_year}] {factor.citation}"
            )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ghg", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    inv = sub.add_parser("inventory", help="calculate emissions and write the report")
    inv.add_argument("--activity", default=DEFAULT_ACTIVITY)
    inv.add_argument("--factors", default=DEFAULT_FACTORS)
    inv.add_argument("--out", default=DEFAULT_OUT)
    inv.add_argument("--stack-config", default="data/stack.json",
                     help="stack/dispersion parameters to embed in the report")
    inv.add_argument("--footprint-km", type=float, default=3.0,
                     help="downwind extent of the plume footprint map, km")
    inv.set_defaults(func=_run_inventory)

    disp = sub.add_parser("dispersion", help="ground-level concentration downwind")
    disp.add_argument("--height", type=float, required=True, help="stack height, m")
    disp.add_argument("--diameter", type=float, default=2.0)
    disp.add_argument("--velocity", type=float, default=12.0, help="exit velocity, m/s")
    disp.add_argument("--exit-temp", type=float, default=400.0, help="K")
    disp.add_argument("--ambient-temp", type=float, default=293.0, help="K")
    disp.add_argument("--emission", type=float, required=True, help="g/s")
    disp.add_argument("--wind", type=float, default=3.0, help="10 m wind, m/s")
    disp.add_argument("--stability", default="D", choices=list("ABCDEF"))
    disp.add_argument("--mixing-height", type=float, default=None, help="m")
    disp.add_argument("--distance", type=float, nargs="+", default=[100, 300, 500, 1000, 2000])
    disp.set_defaults(func=_run_dispersion)

    fac = sub.add_parser("factors", help="print the factor register with citations")
    fac.add_argument("--factors", default=DEFAULT_FACTORS)
    fac.set_defaults(func=_show_factors)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ActivityError, FactorError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
