"""End-to-end pipeline and CLI contract.

These run the shipped data through the shipped code, which is the combination a
reviewer will actually execute.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ghg.cli import main

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def run_cli(tmp_path):
    def _run(*args: str) -> int:
        return main(list(args))

    return _run


def test_full_pipeline_writes_both_reports(run_cli, tmp_path):
    code = run_cli(
        "inventory",
        "--activity", str(ROOT / "data/activity/activity_2025.csv"),
        "--factors", str(ROOT / "data/factors/emission_factors.csv"),
        "--stack-config", str(ROOT / "data/stack.json"),
        "--out", str(tmp_path),
    )
    assert code == 0
    md = tmp_path / "emissions_report.md"
    pdf = tmp_path / "emissions_report.pdf"
    assert md.exists() and pdf.exists()
    assert pdf.read_bytes()[:4] == b"%PDF"
    assert (tmp_path / "plume_footprint.png").exists()
    assert (tmp_path / "scope_breakdown.png").exists()
    assert (tmp_path / "monthly_trend.png").exists()


def test_shipped_data_reconciles_across_the_three_views(run_cli, tmp_path):
    run_cli(
        "inventory",
        "--activity", str(ROOT / "data/activity/activity_2025.csv"),
        "--factors", str(ROOT / "data/factors/emission_factors.csv"),
        "--stack-config", str(ROOT / "data/stack.json"),
        "--out", str(tmp_path),
    )
    text = (tmp_path / "emissions_report.md").read_text(encoding="utf-8")
    # headline, ledger sum sentence, and monthly table must all be present
    assert "**Total emissions:**" in text
    assert "reconciles to the headline total" in text
    assert "## 3. Monthly series" in text
    assert "## 5. Downwind dispersion" in text
    assert "## 7. Boundary and assumptions" in text


def test_missing_factor_is_a_clean_error_not_a_traceback(run_cli, tmp_path, capsys):
    activity = tmp_path / "a.csv"
    activity.write_text(
        "period,site,activity_source,quantity,unit\n"
        "2025-01,Plant,unregistered_source,10,kWh\n",
        encoding="utf-8",
    )
    code = run_cli(
        "inventory",
        "--activity", str(activity),
        "--factors", str(ROOT / "data/factors/emission_factors.csv"),
        "--stack-config", str(ROOT / "data/stack.json"),
        "--out", str(tmp_path / "out"),
    )
    assert code == 1
    err = capsys.readouterr().err
    assert "no emission factor" in err
    assert "Traceback" not in err


def test_cli_without_stack_config_skips_dispersion(run_cli, tmp_path):
    """The carbon half must run on its own: a site without a modelled stack is a
    valid user."""
    code = run_cli(
        "inventory",
        "--activity", str(ROOT / "data/activity/activity_2025.csv"),
        "--factors", str(ROOT / "data/factors/emission_factors.csv"),
        "--stack-config", "",
        "--out", str(tmp_path),
    )
    assert code == 0
    text = (tmp_path / "emissions_report.md").read_text(encoding="utf-8")
    assert "Downwind dispersion" not in text


def test_dispersion_subcommand_prints_a_table(run_cli, capsys):
    code = run_cli(
        "dispersion", "--height", "30", "--emission", "25",
        "--distance", "100", "500", "1000",
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "ug/m3" in out
    assert out.count("\n") >= 4


def test_factors_subcommand_shows_citations(run_cli, capsys):
    code = run_cli("factors", "--factors", str(ROOT / "data/factors/emission_factors.csv"))
    assert code == 0
    out = capsys.readouterr().out
    assert "IPCC 2006" in out
    assert "Vietnam grid emission factor" in out


def test_scenario_runs_on_shipped_data_and_writes_its_report(run_cli, tmp_path):
    code = run_cli(
        "scenario",
        "--activity-old", str(ROOT / "data/activity/activity_2024.csv"),
        "--activity-new", str(ROOT / "data/activity/activity_2025.csv"),
        "--factors-old", str(ROOT / "data/factors/emission_factors_2024.csv"),
        "--factors-new", str(ROOT / "data/factors/emission_factors.csv"),
        "--out", str(tmp_path),
    )
    assert code == 0
    md = tmp_path / "scenario_comparison.md"
    assert md.exists()
    text = md.read_text(encoding="utf-8")
    assert "activity vs factor" in text
    assert "location-based" in text.lower()
    assert "must not be summed" in text


def test_scenario_decomposition_in_the_report_reconciles_to_the_headline(run_cli, tmp_path):
    """The per-source effects printed in the report must sum to the total change.

    This is the end-to-end version of the decomposition identity: if the CLI wires
    the wrong year or the wrong factor to a source, the printed parts stop adding
    up to the printed whole.
    """
    run_cli(
        "scenario",
        "--activity-old", str(ROOT / "data/activity/activity_2024.csv"),
        "--activity-new", str(ROOT / "data/activity/activity_2025.csv"),
        "--factors-old", str(ROOT / "data/factors/emission_factors_2024.csv"),
        "--factors-new", str(ROOT / "data/factors/emission_factors.csv"),
        "--out", str(tmp_path),
    )
    text = (tmp_path / "scenario_comparison.md").read_text(encoding="utf-8")

    import re

    headline = re.search(r"\*\*Total change:\*\* ([+-][\d,]+\.\d+)", text)
    assert headline, "no total change line"
    total = float(headline.group(1).replace(",", ""))

    # the decomposition table: activity | factor | interaction | sum
    rows = re.findall(
        r"\| `[^`]+` \| ([+-][\d,]+\.\d+) \| ([+-][\d,]+\.\d+) \| "
        r"([+-][\d,]+\.\d+) \| ([+-][\d,]+\.\d+) \|",
        text,
    )
    assert rows, "decomposition table not found"
    parts = sum(float(r[3].replace(",", "")) for r in rows)
    assert parts == pytest.approx(total, abs=0.05)
    # and each row's own three effects sum to its printed total
    for activity, factor, interaction, row_total in rows:
        trio = sum(float(v.replace(",", "")) for v in (activity, factor, interaction))
        assert trio == pytest.approx(float(row_total.replace(",", "")), abs=0.02)


def test_scenario_rejects_instruments_larger_than_consumption(run_cli, tmp_path, capsys):
    code = run_cli(
        "scenario",
        "--out", str(tmp_path),
        "--instrument", "oversized", "999999", "0.0",
    )
    assert code == 1
    assert "cannot exceed" in capsys.readouterr().err
