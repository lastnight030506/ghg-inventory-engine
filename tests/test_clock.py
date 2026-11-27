"""Reproducible output.

A report that stamps the wall clock into itself cannot be diffed, so the committed
artifact can never be verified. `SOURCE_DATE_EPOCH` is the reproducible-builds
convention; honouring it is what makes the output checkable.
"""

from __future__ import annotations

import pytest

from ghg.clock import generation_stamp, generation_time

# 2025-12-01 00:00:00 UTC
EPOCH = 1764547200


def test_epoch_is_honoured(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", str(EPOCH))
    monkeypatch.delenv("GHG_BUILD_EPOCH", raising=False)
    assert generation_stamp() == "2025-12-01 00:00 UTC"
    assert generation_time().timestamp() == EPOCH


def test_alias_is_honoured(monkeypatch):
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    monkeypatch.setenv("GHG_BUILD_EPOCH", str(EPOCH))
    assert generation_stamp() == "2025-12-01 00:00 UTC"


def test_source_date_epoch_wins_over_alias(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", str(EPOCH))
    monkeypatch.setenv("GHG_BUILD_EPOCH", str(EPOCH + 86_400))
    assert generation_stamp() == "2025-12-01 00:00 UTC"


def test_blank_values_fall_through_to_the_clock(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "   ")
    monkeypatch.delenv("GHG_BUILD_EPOCH", raising=False)
    # no exception, and a plausible timestamp
    assert generation_time().year >= 2020


@pytest.mark.parametrize("bad", ["not-a-number", "1.5", "", "99999999999999999999"])
def test_invalid_values_raise_a_clear_error(monkeypatch, bad):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", bad)
    monkeypatch.delenv("GHG_BUILD_EPOCH", raising=False)
    if not bad.strip():
        generation_time()  # blank is "unset", not invalid
    else:
        with pytest.raises(ValueError, match="not a valid Unix timestamp"):
            generation_time()


def test_pdf_text_is_stable_across_regeneration(monkeypatch, tmp_path):
    """The PDF's embedded font bytes vary by system; its text must not."""
    from ghg.activity import load_activity
    from ghg.factors import load_factors
    from ghg.inventory import build_inventory
    from ghg.pdf import markdown_to_pdf
    from ghg.report import build_markdown

    monkeypatch.setenv("SOURCE_DATE_EPOCH", str(EPOCH))
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    inventory = build_inventory(
        load_activity(root / "data/activity/activity_2025.csv"),
        load_factors(root / "data/factors/emission_factors.csv"),
    )
    text = build_markdown(inventory, period="2025", site="Plant")

    from pypdf import PdfReader

    first = markdown_to_pdf(text, tmp_path / "a.pdf")
    second = markdown_to_pdf(text, tmp_path / "b.pdf")
    read = lambda p: "\n".join(page.extract_text() or "" for page in PdfReader(p).pages)
    assert read(first) == read(second)
    assert len(PdfReader(first).pages) == len(PdfReader(second).pages)


def test_markdown_and_pdf_are_reproducible(monkeypatch, tmp_path):
    """Byte-identical output for identical input is the whole point."""
    from ghg.activity import load_activity
    from ghg.factors import load_factors
    from ghg.inventory import build_inventory
    from ghg.pdf import markdown_to_pdf
    from ghg.report import build_markdown

    monkeypatch.setenv("SOURCE_DATE_EPOCH", str(EPOCH))
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    records = load_activity(root / "data/activity/activity_2025.csv")
    register = load_factors(root / "data/factors/emission_factors.csv")
    inventory = build_inventory(records, register)

    text_a = build_markdown(inventory, period="2025", site="Plant")
    text_b = build_markdown(inventory, period="2025", site="Plant")
    assert text_a == text_b
    assert "2025-12-01 00:00 UTC" in text_a

    pdf_a = markdown_to_pdf(text_a, tmp_path / "a.pdf")
    pdf_b = markdown_to_pdf(text_a, tmp_path / "b.pdf")
    assert pdf_a.read_bytes() == pdf_b.read_bytes()
