"""Data resolution and CSV hardening.

Two classes of defect that only appear outside a test fixture:

- the default data paths were CWD-relative, so an installed `ghg` could not find
  its own data;
- `csv.DictReader` turns a short row into `None` (AttributeError deep in a
  validator), a spaced header into a "missing column", and a duplicated column
  into a silent last-wins.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ghg import paths
from ghg._csv import CsvFormatError, read_rows
from ghg.activity import ActivityError, load_activity
from ghg.factors import FactorError, load_factors

ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------ path resolution


def test_defaults_resolve_to_existing_files():
    """Whatever mode the package is installed in, the defaults must exist."""
    for path in (
        paths.default_activity(),
        paths.default_activity_previous(),
        paths.default_factors(),
        paths.default_factors_previous(),
        paths.default_stack(),
    ):
        assert Path(path).is_file(), path


def test_data_root_contains_both_subdirectories():
    root = paths.data_root()
    assert (root / "activity").is_dir()
    assert (root / "factors").is_dir()


def test_env_override_is_honoured(tmp_path, monkeypatch):
    (tmp_path / "activity").mkdir()
    (tmp_path / "factors").mkdir()
    monkeypatch.setenv("GHG_DATA_DIR", str(tmp_path))
    assert paths.data_root() == tmp_path
    assert str(tmp_path) in paths.default_factors()


def test_env_override_pointing_nowhere_is_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.setenv("GHG_DATA_DIR", str(tmp_path / "absent"))
    with pytest.raises(FileNotFoundError, match="activity/ and factors/"):
        paths.data_root()


def test_env_override_without_subdirs_is_rejected(tmp_path, monkeypatch):
    """A directory that is not a data root is a typo, not an empty dataset."""
    monkeypatch.setenv("GHG_DATA_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="activity/ and factors/"):
        paths.data_root()


def test_cwd_data_directory_wins_over_bundled(tmp_path, monkeypatch):
    """A checkout or a site's own extract takes precedence over the shipped copy."""
    (tmp_path / "data" / "activity").mkdir(parents=True)
    (tmp_path / "data" / "factors").mkdir(parents=True)
    monkeypatch.delenv("GHG_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert paths.data_root() == tmp_path / "data"


def test_falls_back_to_bundled_when_cwd_has_no_data(tmp_path, monkeypatch):
    monkeypatch.delenv("GHG_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    root = paths.data_root()
    assert (root / "factors").is_dir()


# ------------------------------------------------------------ CSV hardening


def _write(tmp_path, text, name="f.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


HEADER = "period,site,activity_source,quantity,unit\n"


def test_short_row_is_reported_with_a_line_number_not_a_crash(tmp_path):
    """An unclosed quote leaves the row short; csv yields None for the missing
    cells. That used to raise AttributeError from inside parse_quantity."""
    path = _write(tmp_path, HEADER + '2025-01,Plant,"unclosed,1,kWh\n')
    with pytest.raises(ActivityError) as exc:
        load_activity(path)
    assert "line 2" in str(exc.value)
    assert "NoneType" not in str(exc.value)


def test_header_with_surrounding_spaces_is_accepted(tmp_path):
    """Excel exports regularly pad header cells; ' site ' is still the site column."""
    path = _write(tmp_path, "period, site ,activity_source,quantity,unit\n"
                            "2025-01,Plant,grid_electricity,100,kWh\n")
    records = load_activity(path)
    assert records[0].site == "Plant"


def test_duplicate_header_column_is_rejected(tmp_path):
    """DictReader keeps the last of two same-named columns. Which one wins is
    invisible, so the file is ambiguous and refused."""
    path = _write(tmp_path, "period,site,site,activity_source,quantity,unit\n"
                            "2025-01,A,B,grid_electricity,100,kWh\n")
    with pytest.raises(ActivityError, match="duplicate column"):
        load_activity(path)


def test_ragged_row_with_extra_cells_is_rejected(tmp_path):
    path = _write(tmp_path, HEADER + "2025-01,Plant,grid_electricity,100,kWh,extra\n")
    with pytest.raises(ActivityError, match="cells for"):
        load_activity(path)


def test_blank_lines_between_rows_are_skipped(tmp_path):
    path = _write(tmp_path, HEADER + "2025-01,Plant,grid_electricity,100,kWh\n\n"
                                    "2025-02,Plant,grid_electricity,200,kWh\n")
    assert len(load_activity(path)) == 2


def test_crlf_and_bom_are_handled(tmp_path):
    path = _write(tmp_path, "\ufeff" + HEADER.replace("\n", "\r\n")
                  + "2025-01,Plant,grid_electricity,100,kWh\r\n")
    assert load_activity(path)[0].quantity == 100.0


def test_empty_file_names_the_problem(tmp_path):
    path = _write(tmp_path, "")
    with pytest.raises(CsvFormatError, match="empty"):
        list(read_rows(path, ("period",)))


# ------------------------------------------------------------ factor register


FACTOR_HEADER = (
    "activity_source,scope,gas,emission_factor,factor_unit_denominator,"
    "factor_mass_unit,citation,publication_year\n"
)


def test_factor_scope_with_spaces_is_parsed(tmp_path):
    """' 1 ' is what a spreadsheet writes for a numeric cell far more often than
    '1'. int(' 1 ') works, but a stripped read is what makes that reliable."""
    path = _write(tmp_path, FACTOR_HEADER + "diesel_furnace, 1 ,CO2,2.68,L,kg,IPCC 2006,2006\n")
    register = load_factors(path)
    assert register["diesel_furnace"][0].scope == 1


def test_factor_duplicate_column_is_rejected(tmp_path):
    path = _write(
        tmp_path,
        "activity_source,scope,gas,emission_factor,emission_factor,"
        "factor_unit_denominator,factor_mass_unit,citation,publication_year\n"
        "diesel_furnace,1,CO2,2.68,6.66,L,kg,IPCC 2006,2006\n",
    )
    with pytest.raises(FactorError, match="duplicate column"):
        load_factors(path)


def test_factor_csv_structure_error_raises_factor_error(tmp_path):
    """A caller catches FactorError for 'this register is unusable', whatever the
    cause; a CsvFormatError leaking out would break that contract."""
    path = _write(tmp_path, FACTOR_HEADER + "diesel_furnace,1,CO2,2.68,L,kg,IPCC 2006\n")
    with pytest.raises(FactorError):
        load_factors(path)


def test_activity_csv_structure_error_raises_activity_error(tmp_path):
    path = _write(tmp_path, "")
    with pytest.raises(ActivityError):
        load_activity(path)
