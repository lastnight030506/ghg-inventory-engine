"""Scenario comparison: what changed, and what a different Scope 2 method does.

Two questions an analyst is actually asked after the inventory is filed:

1. **Year over year** — did emissions fall because the plant changed, or because
   an emission factor was republished? The second is not a reduction, and a
   report that shows only the total cannot tell them apart.

2. **Location-based versus market-based Scope 2** — the GHG Protocol's Scope 2
   Guidance requires both figures in markets that offer contractual instruments.
   They answer different questions and must never be summed into one number.

This module makes the factor-vs-activity decomposition explicit, because that is
the arithmetic most often got wrong. A naive year-over-year comparison attributes
a grid-factor change to the operator.
"""

from __future__ import annotations

from dataclasses import dataclass

from .activity import ActivityRecord


@dataclass(frozen=True, slots=True)
class Decomposition:
    """Why a source's emissions moved between two periods.

    Three terms that sum exactly to the observed change:

        activity_effect = (Q_new - Q_old) * EF_old
        factor_effect   = Q_old * (EF_new - EF_old)
        interaction     = (Q_new - Q_old) * (EF_new - EF_old)
        total_change    = activity + factor + interaction

    Using Q_new in the factor term instead of Q_old double counts the interaction
    and does not reconcile; `reconciles` catches that, and a test pins it.
    """

    source: str
    quantity_old: float
    quantity_new: float
    factor_old: float
    factor_new: float
    tco2e_old: float
    tco2e_new: float

    @property
    def activity_effect(self) -> float:
        return (self.quantity_new - self.quantity_old) * self.factor_old

    @property
    def factor_effect(self) -> float:
        return self.quantity_old * (self.factor_new - self.factor_old)

    @property
    def interaction(self) -> float:
        return (self.quantity_new - self.quantity_old) * (self.factor_new - self.factor_old)

    @property
    def total_change(self) -> float:
        return self.tco2e_new - self.tco2e_old

    def reconciles(self, *, abs_tol: float = 1e-9) -> bool:
        """The three effects must sum to the observed change, or the maths is wrong."""
        return abs(
            (self.activity_effect + self.factor_effect + self.interaction) - self.total_change
        ) <= abs_tol


def decompose(
    source: str,
    quantity_old: float,
    quantity_new: float,
    factor_old: float,
    factor_new: float,
    *,
    gwp: float = 1.0,
    mass_multiplier: float = 1.0,
) -> Decomposition:
    """Build the decomposition for one source and assert it reconciles.

    `gwp` and `mass_multiplier` fold the tCO2e conversion into the factors so the
    caller passes the effective factor it already has.
    """
    eff_old = factor_old * mass_multiplier * gwp / 1000.0
    eff_new = factor_new * mass_multiplier * gwp / 1000.0
    result = Decomposition(
        source=source,
        quantity_old=quantity_old,
        quantity_new=quantity_new,
        factor_old=eff_old,
        factor_new=eff_new,
        tco2e_old=quantity_old * eff_old,
        tco2e_new=quantity_new * eff_new,
    )
    if not result.reconciles():
        raise AssertionError(f"{source}: decomposition does not reconcile to the total change")
    return result


def annual_quantity(records: list[ActivityRecord], source: str, year: int) -> float:
    """Sum one source's activity for a year. Missing year is zero activity, not an error."""
    return sum(r.quantity for r in records if r.activity_source == source and r.year == year)


def classify_change(decomposition: Decomposition, *, threshold: float = 0.02) -> str:
    """Name the dominant driver, so the report can say it in a sentence.

    `threshold` is the share of |total change| an effect must reach to be called
    dominant; below it, the change is described as mixed.
    """
    total = abs(decomposition.total_change)
    if total < 1e-9:
        return "no change"
    shares = {
        "activity": abs(decomposition.activity_effect) / total,
        "factor": abs(decomposition.factor_effect) / total,
        "interaction": abs(decomposition.interaction) / total,
    }
    driver, share = max(shares.items(), key=lambda item: item[1])
    return driver if share >= threshold else "mixed"


# ---------------------------------------------------------------- Scope 2 methods


@dataclass(frozen=True, slots=True)
class ContractualInstrument:
    """One energy attribute certificate or contract covering part of a year.

    Both fields are required. A market-based factor with no instrument behind it
    is a guess with a decimal point, and the GHG Protocol's requirement is that a
    market-based figure be supported by instruments the company can evidence.
    """

    name: str
    mwh: float
    emission_factor_kg_per_kwh: float

    def __post_init__(self) -> None:
        if self.mwh < 0:
            raise ValueError(f"{self.name}: mwh must be >= 0")
        if self.emission_factor_kg_per_kwh < 0:
            raise ValueError(f"{self.name}: emission factor must be >= 0")
        if not self.name.strip():
            raise ValueError("instrument must be named; an unnamed instrument is unauditable")


@dataclass(frozen=True, slots=True)
class Scope2Dual:
    """The two Scope 2 figures the Guidance requires, side by side.

    They are not alternatives to be chosen between and never summed. Location-based
    describes the grid the plant draws from; market-based describes the contracts
    it holds. A residual grid factor covers unbundled consumption.
    """

    consumption_kwh: float
    grid_factor_kg_per_kwh: float
    instruments: tuple[ContractualInstrument, ...]
    residual_factor_kg_per_kwh: float

    @property
    def location_tco2e(self) -> float:
        return self.consumption_kwh * self.grid_factor_kg_per_kwh / 1000.0

    @property
    def instrumented_kwh(self) -> float:
        return sum(i.mwh for i in self.instruments) * 1000.0

    @property
    def residual_kwh(self) -> float:
        residual = self.consumption_kwh - self.instrumented_kwh
        if residual < -1e-6:
            raise ValueError(
                f"contractual instruments cover {self.instrumented_kwh:,.0f} kWh but "
                f"consumption is {self.consumption_kwh:,.0f} kWh; certificates cannot "
                "exceed the electricity consumed"
            )
        return max(residual, 0.0)

    @property
    def market_tco2e(self) -> float:
        covered = sum(i.mwh * 1000.0 * i.emission_factor_kg_per_kwh for i in self.instruments) / 1000.0
        return covered + self.residual_kwh * self.residual_factor_kg_per_kwh / 1000.0

    @property
    def coverage(self) -> float:
        return self.instrumented_kwh / self.consumption_kwh if self.consumption_kwh else 0.0

    def describe(self) -> str:
        if not self.instruments:
            return (
                "No contractual instruments: market-based Scope 2 equals the residual "
                "factor and is not a reduction against location-based."
            )
        return (
            f"{self.coverage:.1%} of consumption covered by "
            f"{len(self.instruments)} instrument(s); the remainder uses the residual "
            f"grid factor."
        )
