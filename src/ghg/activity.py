"""Activity data ingestion and validation.

Activity data is the "how much did we consume" half of a GHG inventory and the
half that a human types into a spreadsheet. Every field here is validated at the
boundary: a silently dropped row or a unit typo is invisible in the final total,
which is exactly the failure mode manual spreadsheets have.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

from ._csv import CsvFormatError, read_rows

PERIOD_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")

REQUIRED_COLUMNS = ("period", "site", "activity_source", "quantity", "unit")

# Canonical unit spellings. Aliases exist because meters, invoices and fuel
# dockets all label the same thing differently; the mapping is explicit so a
# typo fails loudly instead of landing in an unknown-unit row.
UNIT_ALIASES = {
    "kwh": "kWh",
    "mwh": "MWh",
    "gwh": "GWh",
    "l": "L",
    "litre": "L",
    "liter": "L",
    "litres": "L",
    "liters": "L",
    "m3": "m3",
    "t": "t",
    "tonne": "t",
    "tonnes": "t",
    "metric ton": "t",
    "kg": "kg",
    "tkm": "tkm",
    "tonne-km": "tkm",
    "t.km": "tkm",
}


class ActivityError(ValueError):
    """Raised for any activity row that cannot be trusted. Never partial."""


@dataclass(frozen=True, slots=True)
class ActivityRecord:
    period: str
    site: str
    activity_source: str
    quantity: float
    unit: str
    line: int

    @property
    def year(self) -> int:
        return int(self.period[:4])

    @property
    def month(self) -> int:
        return int(self.period[5:7])


def canonical_unit(raw: str, *, line: int) -> str:
    key = " ".join(raw.split()).lower()
    try:
        return UNIT_ALIASES[key]
    except KeyError:
        known = ", ".join(sorted(set(UNIT_ALIASES.values())))
        raise ActivityError(f"line {line}: unknown unit {raw!r}; accepted units: {known}") from None


def parse_quantity(raw: str, *, line: int) -> float:
    text = raw.strip().replace(",", "")
    if not text:
        raise ActivityError(f"line {line}: quantity is blank")
    try:
        value = float(text)
    except ValueError:
        raise ActivityError(f"line {line}: quantity {raw!r} is not a number") from None
    if not math.isfinite(value):
        raise ActivityError(f"line {line}: quantity {raw!r} is not finite")
    if value < 0:
        raise ActivityError(
            f"line {line}: quantity {value} is negative; removals and credits are "
            "outside an inventory built for a gross-emissions filing"
        )
    return value


def parse_period(raw: str, *, line: int) -> str:
    text = raw.strip()
    if not PERIOD_RE.match(text):
        raise ActivityError(
            f"line {line}: period {raw!r} is not an ISO month (YYYY-MM); "
            "quarterly or annual labels must be allocated upstream"
        )
    return text


def load_activity(path: str | Path) -> list[ActivityRecord]:
    """Read an activity CSV. Raises on the first untrustworthy row."""
    path = Path(path)
    if not path.exists():
        raise ActivityError(f"activity file not found: {path}")

    records: list[ActivityRecord] = []
    try:
        rows = read_rows(path, REQUIRED_COLUMNS)
        for line, row in rows:
            records.append(
                ActivityRecord(
                    period=parse_period(row["period"], line=line),
                    site=row["site"].strip(),
                    activity_source=row["activity_source"].strip(),
                    quantity=parse_quantity(row["quantity"], line=line),
                    unit=canonical_unit(row["unit"], line=line),
                    line=line,
                )
            )
    except CsvFormatError as exc:
        # Re-raised as ActivityError so callers catch one exception type for "this
        # file cannot be trusted", whether the problem is structural or a value.
        raise ActivityError(str(exc)) from None

    if not records:
        raise ActivityError(f"{path.name}: no activity rows found")
    for record in records:
        if not record.site:
            raise ActivityError(f"line {record.line}: site is blank")
        if not record.activity_source:
            raise ActivityError(f"line {record.line}: activity_source is blank")
    return records
