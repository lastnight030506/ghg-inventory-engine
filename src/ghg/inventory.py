"""The inventory: join, convert, aggregate.

The order of operations is the accounting contract. Validation runs to completion
before any arithmetic, so a run either produces a fully reconciled ledger or
raises. A total cannot be assembled from rows that failed a gate.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .activity import ActivityRecord
from .factors import GWP_STANDARD, EmissionFactor, FactorError

# Activity unit -> the factor denominator unit that consumes it. Exact strings,
# no conversion: kWh and MWh are both valid inputs but the factor says which one
# it expects, and a mismatch is a 1000x error that a plausible total hides.
COMPATIBLE_UNITS: dict[str, tuple[str, ...]] = {
    "L": ("L",),
    "m3": ("m3",),
    "kg": ("kg",),
    "t": ("t",),
    "kWh": ("kWh",),
    "MWh": ("MWh",),
    "GWh": ("GWh",),
    "tkm": ("tkm",),
}


@dataclass(frozen=True, slots=True)
class EmissionLine:
    """One gas, one source, one month. The atomic auditable record."""

    period: str
    site: str
    activity_source: str
    scope: int
    gas: str
    quantity: float
    activity_unit: str
    emission_factor: float
    factor_denominator: str
    factor_mass_unit: str
    mass_emitted_kg: float
    gwp100: float
    tco2e: float
    citation: str
    publication_year: int


@dataclass(frozen=True, slots=True)
class Inventory:
    lines: tuple[EmissionLine, ...]
    gwp_standard: str = GWP_STANDARD

    @property
    def total_tco2e(self) -> float:
        return sum(line.tco2e for line in self.lines)

    def by_scope(self) -> dict[int, float]:
        totals: dict[int, float] = defaultdict(float)
        for line in self.lines:
            totals[line.scope] += line.tco2e
        return dict(sorted(totals.items()))

    def by_month_scope(self) -> dict[tuple[str, int], float]:
        totals: dict[tuple[str, int], float] = defaultdict(float)
        for line in self.lines:
            totals[(line.period, line.scope)] += line.tco2e
        return dict(sorted(totals.items()))

    def by_source(self) -> dict[str, float]:
        totals: dict[str, float] = defaultdict(float)
        for line in self.lines:
            totals[line.activity_source] += line.tco2e
        return dict(sorted(totals.items(), key=lambda item: -item[1]))


def _resolve_factor(record: ActivityRecord, register: dict[str, list[EmissionFactor]]) -> list[EmissionFactor]:
    factors = register.get(record.activity_source)
    if not factors:
        known = ", ".join(sorted(register))
        raise FactorError(
            f"line {record.line}: no emission factor for activity_source "
            f"{record.activity_source!r}; registered sources: {known}"
        )
    expected = COMPATIBLE_UNITS[record.unit]
    bad = [f for f in factors if f.denominator not in expected]
    if bad:
        detail = ", ".join(f"{f.gas}:{f.denominator}" for f in bad)
        raise FactorError(
            f"line {record.line}: {record.activity_source} activity is in {record.unit} "
            f"but its factor denominator is {detail}; convert the activity data "
            "explicitly upstream rather than letting the number be reinterpreted"
        )
    return factors


def build_inventory(
    records: list[ActivityRecord], register: dict[str, list[EmissionFactor]]
) -> Inventory:
    """Join activity to factors and convert to tCO2e. Fails closed."""
    lines: list[EmissionLine] = []
    for record in records:
        for factor in _resolve_factor(record, register):
            lines.append(
                EmissionLine(
                    period=record.period,
                    site=record.site,
                    activity_source=record.activity_source,
                    scope=factor.scope,
                    gas=factor.gas,
                    quantity=record.quantity,
                    activity_unit=record.unit,
                    emission_factor=factor.emission_factor,
                    factor_denominator=factor.denominator,
                    factor_mass_unit=factor.mass_unit,
                    mass_emitted_kg=factor.mass_kg(record.quantity),
                    gwp100=factor.gwp,
                    tco2e=factor.tco2e(record.quantity),
                    citation=factor.citation,
                    publication_year=factor.publication_year,
                )
            )

    if not lines:
        raise FactorError("no emission lines produced; check the activity file")
    return Inventory(lines=tuple(lines))
