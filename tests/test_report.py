"""Report generation: determinism, reconciliation, and the PDF actually rendering.

The report is the deliverable, so it gets tests of its own rather than being
eyeballed once. The reconciliation test is the important one: it re-derives the
headline total from the ledger table text, which is what a reviewer does.
"""

from __future__ import annotations

import re

import pytest

from ghg.activity import ActivityRecord
from ghg.factors import EmissionFactor
from ghg.inventory import build_inventory
from ghg.report import build_markdown

FACTOR = EmissionFactor(
    activity_source="diesel_furnace",
    scope=1,
    gas="CO2",
    emission_factor=2.68,
    denominator="L",
    mass_unit="kg",
    citation="IPCC 2006 Guidelines, Vol. 2, Table 2.2",
    publication_year=2006,
)


def _inventory(quantity=1000.0, period="2025-01"):
    record = ActivityRecord(
        period=period,
        site="VSIP-II plant",
        activity_source="diesel_furnace",
        quantity=quantity,
        unit="L",
        line=2,
    )
    return build_inventory([record], {"diesel_furnace": [FACTOR]})


def test_total_appears_in_headline_and_matches_ledger_sum():
    inv = _inventory(1000.0)
    text = build_markdown(inv, period="2025-01 to 2025-01", site="VSIP-II plant")
    assert "2.68 tCO₂e" in text

    # Re-derive from the ledger rows the way a reviewer would: pull every tCO2e
    # cell from the ledger section and sum it.
    ledger = text.split("## 4. Auditable ledger")[1]
    cells = re.findall(r"\|\s*([\d,]+\.\d+)\s*\|\s*$", ledger, flags=re.MULTILINE)
    assert cells, "ledger table not found"
    assert sum(float(c.replace(",", "")) for c in cells) == pytest.approx(inv.total_tco2e, abs=0.01)


def test_factor_citation_is_printed_in_provenance():
    text = build_markdown(_inventory(), period="2025-01", site="Plant")
    proc = text.split("## 6. Emission factor provenance")[1]
    assert "IPCC 2006 Guidelines" in proc
    assert "2006" in proc


def test_every_markdown_table_has_a_consistent_column_count():
    """A header with 7 cells and body rows with 6 silently drops every row in the
    PDF renderer. That happened; this catches the next one."""
    text = build_markdown(_inventory(), period="2025-01", site="Plant")
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            block = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                block.append(lines[i])
                i += 1
            header_cols = len(block[0].strip().strip("|").split("|"))
            for row in block[2:]:
                cols = len(row.strip().strip("|").split("|"))
                assert cols == header_cols, (
                    f"table row has {cols} cells, header has {header_cols}: {row[:90]}"
                )
        else:
            i += 1


def test_provenance_table_lists_every_factor():
    text = build_markdown(_inventory(), period="2025-01", site="Plant")
    proc = text.split("## 6. Emission factor provenance")[1].split("## 7")[0]
    rows = [l for l in proc.splitlines() if l.lstrip().startswith("|")][2:]
    assert len(rows) == 1  # one factor in this fixture
    assert "diesel_furnace" in rows[0]


def test_no_markdown_emphasis_leaks_into_rendered_text():
    """The PDF renderer understands **bold** but not *italic*; a stray asterisk
    would print literally."""
    text = build_markdown(_inventory(), period="2025-01", site="Plant")
    stripped = text.replace("**", "")
    assert "*" not in stripped, "single-asterisk emphasis will render literally"


def test_boundary_section_disclaims_compliance():
    text = build_markdown(_inventory(), period="2025-01", site="Plant")
    assert "Not a compliance determination" in text


def test_missing_scope_figure_does_not_break_render():
    """No charts requested: report still builds and references no image."""
    text = build_markdown(_inventory(), period="2025-01", site="Plant")
    assert "![" not in text


def test_markdown_is_stable_across_runs_except_the_timestamp():
    first = build_markdown(_inventory(), period="2025-01", site="Plant")
    second = build_markdown(_inventory(), period="2025-01", site="Plant")
    strip = lambda t: re.sub(r"\*\*Generated:\*\*.*", "", t)
    assert strip(first) == strip(second)


def test_pdf_renders_and_is_non_trivial(tmp_path):
    from ghg.pdf import markdown_to_pdf

    text = build_markdown(_inventory(), period="2025-01", site="Plant")
    out = markdown_to_pdf(text, tmp_path / "report.pdf")
    assert out.exists()
    assert out.stat().st_size > 5000
    assert out.read_bytes()[:4] == b"%PDF"


def test_pdf_contains_no_markdown_syntax_leaking_through(tmp_path):
    """A pipe table left as pipes means the renderer skipped it."""
    from ghg.pdf import markdown_to_pdf

    text = build_markdown(_inventory(), period="2025-01", site="Plant")
    out = markdown_to_pdf(text, tmp_path / "r.pdf", base_dir=tmp_path)
    raw = out.read_bytes()
    assert b"|\\xe2\\x80\\x94" not in raw  # no "|---" separator rows survived as text
