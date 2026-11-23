"""Emission factor registry.

Factors live in a CSV, not in Python, for one reason: an auditor has to be able to
read the factor register next to the report and check each number against the
document it came from. The loader therefore refuses any row without complete
provenance — a factor with no citation is an unusable factor, and a factor
quietly defaulted is worse than a crash.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

# IPCC AR6 WG1 Table 7.15, 100-year horizon. Do not extend from memory: adding a
# gas is a documented change carrying its own citation and test.
GWP_STANDARD = "IPCC AR6 WG1, 100-year (Table 7.15)"
GWP100_AR6: dict[str, float] = {
    "CO2": 1.0,
    "CO2e": 1.0,
    "CH4_fossil": 29.8,
    "CH4_non_fossil": 27.0,
    "N2O": 273.0,
}

MASS_TO_KG: dict[str, float] = {"kg": 1.0, "g": 0.001, "t": 1000.0}

FACTOR_COLUMNS = (
    "activity_source",
    "scope",
    "gas",
    "emission_factor",
    "factor_unit_denominator",
    "factor_mass_unit",
    "citation",
    "publication_year",
)


class FactorError(ValueError):
    """Raised when the factor register is incomplete or ambiguous."""


@dataclass(frozen=True, slots=True)
class EmissionFactor:
    activity_source: str
    scope: int
    gas: str
    emission_factor: float
    denominator: str
    mass_unit: str
    citation: str
    publication_year: int

    @property
    def gwp(self) -> float:
        return GWP100_AR6[self.gas]

    def mass_kg(self, quantity: float) -> float:
        """Mass of this gas released, in kg. Single source of the unit maths."""
        return quantity * self.emission_factor * MASS_TO_KG[self.mass_unit]

    def tco2e(self, quantity: float) -> float:
        """tCO2e for `quantity` expressed in this factor's denominator unit."""
        return self.mass_kg(quantity) * self.gwp / 1000.0


def _require(record: dict[str, str], names: tuple[str, ...], line: int, path: Path) -> None:
    blank = [name for name in names if not (record.get(name) or "").strip()]
    if blank:
        raise FactorError(f"{path.name} line {line}: blank required field(s) {blank}")


def load_factors(path: str | Path) -> dict[str, list[EmissionFactor]]:
    """Load the factor register, keyed by activity_source.

    One source maps to a list because a fuel emits CO2, CH4 and N2O; each gas is
    a separate line with its own GWP. Duplicate (source, gas) pairs are rejected:
    two factors for one gas would double count silently.
    """
    path = Path(path)
    if not path.exists():
        raise FactorError(f"factor register not found: {path}")

    by_source: dict[str, list[EmissionFactor]] = {}
    seen: set[tuple[str, str]] = set()

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        header = tuple(reader.fieldnames or ())
        missing = [name for name in FACTOR_COLUMNS if name not in header]
        if missing:
            raise FactorError(f"{path.name}: missing columns {missing}; got {list(header)}")

        for line, row in enumerate(reader, start=2):
            _require(row, FACTOR_COLUMNS, line, path)

            gas = row["gas"].strip()
            if gas not in GWP100_AR6:
                raise FactorError(
                    f"{path.name} line {line}: gas {gas!r} has no AR6 GWP100 value; "
                    f"known gases: {sorted(GWP100_AR6)}"
                )

            mass_unit = row["factor_mass_unit"].strip()
            if mass_unit not in MASS_TO_KG:
                raise FactorError(
                    f"{path.name} line {line}: factor_mass_unit {mass_unit!r} must be "
                    f"one of {sorted(MASS_TO_KG)}"
                )

            try:
                scope = int(row["scope"])
                year = int(row["publication_year"])
                value = float(row["emission_factor"])
            except ValueError as exc:
                raise FactorError(f"{path.name} line {line}: non-numeric field ({exc})") from None

            if scope not in (1, 2, 3):
                raise FactorError(f"{path.name} line {line}: scope {scope} not in 1,2,3")
            if not 1990 <= year <= 2100:
                raise FactorError(f"{path.name} line {line}: publication_year {year} implausible")
            if not math.isfinite(value) or value < 0:
                raise FactorError(
                    f"{path.name} line {line}: emission_factor {value} must be finite and >= 0"
                )

            source = row["activity_source"].strip()
            key = (source, gas)
            if key in seen:
                raise FactorError(
                    f"{path.name} line {line}: duplicate factor for {key}; "
                    "one row per gas per source"
                )
            seen.add(key)

            by_source.setdefault(source, []).append(
                EmissionFactor(
                    activity_source=source,
                    scope=scope,
                    gas=gas,
                    emission_factor=value,
                    denominator=row["factor_unit_denominator"].strip(),
                    mass_unit=mass_unit,
                    citation=row["citation"].strip(),
                    publication_year=year,
                )
            )

    if not by_source:
        raise FactorError(f"{path.name}: register is empty")
    return by_source
