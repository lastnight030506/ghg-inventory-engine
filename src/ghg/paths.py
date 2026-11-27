"""Where the bundled data lives, and how the CLI resolves it.

The defaults used to be CWD-relative strings (`data/activity/...`). That works
from the repo root and fails the moment the tool is installed and run anywhere
else — `pip install ghg-inventory-engine && ghg inventory` raised "factor register
not found". The data is package data now, so the resolver asks the package where
it is.

Resolution order, so a site can override the shipped sample without editing an
installed package:

1. an explicit path given on the command line (never resolved here);
2. `$GHG_DATA_DIR`, if set;
3. a `data/` directory beside the current working directory, so a checkout is
   used in preference to the copy inside site-packages;
4. the `ghg/data/` directory shipped inside the package.
"""

from __future__ import annotations

import os
from pathlib import Path

_HERE = Path(__file__).resolve().parent
# In a built wheel the data sits inside the package; in a source checkout it sits
# at the repo root, three levels up from this file. Both are checked so
# `pip install -e .` and `pip install .` behave the same.
PACKAGE_DATA = _HERE / "data"
CHECKOUT_DATA = _HERE.parent.parent / "data"

_ACTIVITY = "activity/activity_2025.csv"
_ACTIVITY_PREV = "activity/activity_2024.csv"
_FACTORS = "factors/emission_factors.csv"
_FACTORS_PREV = "factors/emission_factors_2024.csv"
_STACK = "stack.json"


def _looks_like_data_dir(path: Path) -> bool:
    return (path / "factors").is_dir() and (path / "activity").is_dir()


def data_root() -> Path:
    """The directory that holds `activity/`, `factors/` and `stack.json`."""
    override = os.environ.get("GHG_DATA_DIR")
    if override:
        candidate = Path(override).expanduser()
        if not _looks_like_data_dir(candidate):
            raise FileNotFoundError(
                f"GHG_DATA_DIR does not contain activity/ and factors/: {candidate}"
            )
        return candidate

    # A working directory that has its own data/ wins, so a site can point the
    # tool at its own extract by cd-ing there or by setting GHG_DATA_DIR.
    cwd_candidate = Path.cwd() / "data"
    if _looks_like_data_dir(cwd_candidate):
        return cwd_candidate

    for bundled in (PACKAGE_DATA, CHECKOUT_DATA):
        if _looks_like_data_dir(bundled):
            return bundled

    raise FileNotFoundError(
        "no bundled data directory found; set GHG_DATA_DIR or pass --activity/--factors"
    )


def default_activity() -> str:
    return str(data_root() / _ACTIVITY)


def default_activity_previous() -> str:
    return str(data_root() / _ACTIVITY_PREV)


def default_factors() -> str:
    return str(data_root() / _FACTORS)


def default_factors_previous() -> str:
    return str(data_root() / _FACTORS_PREV)


def default_stack() -> str:
    return str(data_root() / _STACK)
