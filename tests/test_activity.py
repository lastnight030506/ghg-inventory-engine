"""Activity data validation.

The failure this guards against is the spreadsheet failure: a row silently
dropped, a unit reinterpreted, a negative quantity netted into a total. Each test
below is one way that happens.
"""

from __future__ import annotations

import pytest

from ghg.activity import ActivityError, load_activity


def _write(tmp_path, text):
    path = tmp_path / "activity.csv"
    path.write_text(text, encoding="utf-8")
    return path


HEADER = "period,site,activity_source,quantity,unit\n"


def test_loads_valid_rows_and_canonicalises_units(tmp_path):
    path = _write(
        tmp_path,
        HEADER
        + "2025-01,Plant A,grid_electricity,120000,KWH\n"
        + "2025-01,Plant A,diesel_furnace,5000,litres\n",
    )
    records = load_activity(path)
    assert [r.unit for r in records] == ["kWh", "L"]
    assert records[0].quantity == 120000
    assert records[0].year == 2025 and records[0].month == 1


def test_thousands_separator_is_accepted_not_silently_dropped(tmp_path):
    path = _write(tmp_path, HEADER + '"2025-01",Plant,"grid_electricity","120,000",kWh\n')
    assert load_activity(path)[0].quantity == 120000.0


@pytest.mark.parametrize("period", ["2025-Q1", "2025", "2025-13", "2025-1", "", "Jan 2025"])
def test_non_monthly_periods_are_rejected(tmp_path, period):
    path = _write(tmp_path, HEADER + f"{period},Plant,grid_electricity,100,kWh\n")
    with pytest.raises(ActivityError, match="ISO month"):
        load_activity(path)


def test_unknown_unit_fails_and_names_accepted_units(tmp_path):
    path = _write(tmp_path, HEADER + "2025-01,Plant,diesel_furnace,100,gallons\n")
    with pytest.raises(ActivityError, match="unknown unit"):
        load_activity(path)


def test_negative_quantity_is_rejected_as_out_of_scope(tmp_path):
    path = _write(tmp_path, HEADER + "2025-01,Plant,grid_electricity,-50,kWh\n")
    with pytest.raises(ActivityError, match="negative"):
        load_activity(path)


def test_non_numeric_and_non_finite_quantities_are_rejected(tmp_path):
    for bad in ["abc", "nan", "inf"]:
        path = _write(tmp_path, HEADER + f"2025-01,Plant,grid_electricity,{bad},kWh\n")
        with pytest.raises(ActivityError):
            load_activity(path)


def test_missing_column_names_the_column(tmp_path):
    path = _write(tmp_path, "period,site,quantity,unit\n2025-01,Plant,1,kWh\n")
    with pytest.raises(ActivityError, match="activity_source"):
        load_activity(path)


def test_empty_file_is_an_error_not_an_empty_inventory(tmp_path):
    path = _write(tmp_path, HEADER)
    with pytest.raises(ActivityError, match="no activity rows"):
        load_activity(path)


def test_blank_site_is_rejected(tmp_path):
    path = _write(tmp_path, HEADER + "2025-01,,grid_electricity,100,kWh\n")
    with pytest.raises(ActivityError, match="site"):
        load_activity(path)
