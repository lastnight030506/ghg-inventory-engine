"""Gaussian plume dispersion.

Why a dispersion module sits next to a carbon ledger
----------------------------------------------------
A GHG inventory says how many tonnes left the stack. It says nothing about where
they went or how a co-pollutant (NOx, SO2, particulate) lands on the neighbours.
For an exporting manufacturer answering CBAM for Brussels and a local air permit
for the province at the same time, those are the same stack and the same day's
wind. This module answers the second question with the standard regulatory
screening model.

Model and its limits
--------------------
Continuous point source, steady wind, flat terrain, no chemistry, no deposition,
no building downwash. Concentration is Gaussian in the crosswind direction and
Gaussian in the vertical, with reflection at the ground and — when a mixing
height is supplied — at the inversion lid. Pasquill-Gifford classes with Briggs
dispersion coefficients; plume rise by Holland with the Briggs stack-tip
downwash correction.

This is the model regulators use for a first pass and for permit screening. It is
not a substitute for a site-specific AERMOD/ADMS run, which is what an EIA
actually requires. Every function here is deterministic and checked against hand
arithmetic in the tests; that makes it auditable, not physically complete.

Units are held consistently: metres, seconds, kelvin, grams per second in, and
micrograms per cubic metre out.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Classes A (very unstable) .. F (stable).
STABILITY_CLASSES = ("A", "B", "C", "D", "E", "F")

# Briggs open-country coefficients: sigma = a*x*(1+b*x)^c
# Each entry is (a_y, b_y, c_y, a_z, b_z, c_z) with x and sigma in metres.
_BRIGGS_OPEN: dict[str, tuple[float, float, float, float, float, float]] = {
    "A": (0.22, 0.0001, -0.5, 0.20, 0.0, 0.0),
    "B": (0.16, 0.0001, -0.5, 0.12, 0.0, 0.0),
    "C": (0.11, 0.0001, -0.5, 0.08, 0.0002, -0.5),
    "D": (0.08, 0.0001, -0.5, 0.06, 0.0015, -0.5),
    "E": (0.06, 0.0001, -0.5, 0.03, 0.0003, -1.0),
    "F": (0.04, 0.0001, -0.5, 0.016, 0.0003, -1.0),
}

# Briggs urban coefficients, same layout. Urban sigma grows faster near the
# source because building-generated turbulence is already present at release.
_BRIGGS_URBAN: dict[str, tuple[float, float, float, float, float, float]] = {
    "A": (0.32, 0.0004, -0.5, 0.24, 0.001, 0.5),
    "B": (0.32, 0.0004, -0.5, 0.24, 0.001, 0.5),
    "C": (0.22, 0.0004, -0.5, 0.20, 0.0, 0.0),
    "D": (0.16, 0.0004, -0.5, 0.14, 0.0003, -0.5),
    "E": (0.11, 0.0004, -0.5, 0.08, 0.00015, -0.5),
    "F": (0.11, 0.0004, -0.5, 0.08, 0.00015, -0.5),
}

# Wind-profile exponent for u(z) = u10*(z/10)^p, by stability class. Two sets,
# because the standard table gives them separately and the difference is not
# small: at a 30 m stack in class F the rural exponent gives 24% less wind than
# the urban one, and concentration is inversely proportional to wind speed.
_WIND_EXPONENT_RURAL: dict[str, float] = {
    "A": 0.07, "B": 0.07, "C": 0.10, "D": 0.15, "E": 0.35, "F": 0.55,
}
_WIND_EXPONENT_URBAN: dict[str, float] = {
    "A": 0.15, "B": 0.15, "C": 0.20, "D": 0.25, "E": 0.30, "F": 0.30,
}

# Pasquill stability from 10 m wind speed and insolation (day) / cloud (night).
# Rows: wind speed upper bound in m/s. Columns: strong, moderate, slight, and the
# two night cases (thin cloud >= 4/8, clear < 3/8).
# shortcut: the standard table has intermediate cells (A-B, B-C, C-D) that this
# implementation rounds to the more unstable class, because the Briggs fits are
# defined per class and interpolating sigma between two classes has no standard
# form. Rounding unstable is conservative for plume rise and mixing depth but not
# for peak ground-level concentration; upgrade to a class-interpolating scheme if
# a permit hinges on the B-C / C-D boundary condition.
_PASQUILL_DAY = (
    (2.0, "A", "A", "B"),
    (3.0, "A", "B", "C"),
    (5.0, "B", "B", "C"),
    (6.0, "C", "C", "D"),
    (float("inf"), "C", "D", "D"),
)
_PASQUILL_NIGHT = (
    (2.0, "F", "F"),
    (3.0, "E", "F"),
    (5.0, "D", "E"),
    (6.0, "D", "D"),
    (float("inf"), "D", "D"),
)


@dataclass(frozen=True, slots=True)
class Stack:
    """Physical stack and exhaust parameters."""

    height_m: float
    diameter_m: float
    exit_velocity_ms: float
    exit_temperature_k: float
    ambient_temperature_k: float

    def __post_init__(self) -> None:
        for name in ("height_m", "diameter_m", "exit_velocity_ms"):
            if getattr(self, name) <= 0:
                raise ValueError(f"stack {name} must be positive")
        for name in ("exit_temperature_k", "ambient_temperature_k"):
            if getattr(self, name) <= 0:
                raise ValueError(f"stack {name} must be in kelvin and positive")

    @property
    def area_m2(self) -> float:
        return math.pi * (self.diameter_m / 2.0) ** 2

    @property
    def volumetric_flow_m3s(self) -> float:
        return self.exit_velocity_ms * self.area_m2

    @property
    def buoyancy_flux_m4s3(self) -> float:
        """Briggs buoyancy flux Fb, m^4/s^3. Zero for a cold release."""
        delta_t = self.exit_temperature_k - self.ambient_temperature_k
        g = 9.80665
        return g * self.exit_velocity_ms * (self.diameter_m / 2.0) ** 2 * delta_t / self.exit_temperature_k

    @property
    def momentum_flux_m4s2(self) -> float:
        """Briggs momentum flux Fm, m^4/s^2."""
        return self.exit_velocity_ms**2 * (self.diameter_m / 2.0) ** 2 * (
            self.ambient_temperature_k / self.exit_temperature_k
        )


@dataclass(frozen=True, slots=True)
class PlumeState:
    """Everything needed to evaluate concentration at a receptor."""

    stack: Stack
    emission_rate_gs: float
    wind_speed_10m_ms: float
    stability: str
    mixing_height_m: float | None = None
    urban: bool = False

    def __post_init__(self) -> None:
        if self.emission_rate_gs < 0:
            raise ValueError("emission_rate_gs must be >= 0")
        if self.wind_speed_10m_ms <= 0:
            raise ValueError("wind_speed_10m_ms must be > 0")
        if self.stability not in STABILITY_CLASSES:
            raise ValueError(f"stability must be one of {STABILITY_CLASSES}, got {self.stability!r}")
        if self.mixing_height_m is not None and self.mixing_height_m <= self.stack.height_m:
            raise ValueError("mixing_height_m must be above the physical stack top")


def wind_at_height(wind_10m_ms: float, height_m: float, stability: str, *, urban: bool = False) -> float:
    """Power-law wind profile. A stack rarely sees the 10 m anemometer's wind."""
    table = _WIND_EXPONENT_URBAN if urban else _WIND_EXPONENT_RURAL
    exponent = table[stability]
    return wind_10m_ms * (max(height_m, 10.0) / 10.0) ** exponent


def stack_tip_downwash_m(stack: Stack, wind_ms: float) -> float:
    """Briggs (1973) stack-tip downwash, as a change to the physical stack height.

        h' = h + 2*[(vs/u) - 1.5]*d    for vs < 1.5u, else h' = h

    This LOWERS the physical stack height — it is a negative correction, not a
    raised exit velocity. The distinction matters: raising vs would credit a lazy
    plume with extra momentum and buoyant rise, under-predicting ground-level
    concentration for exactly the low-velocity stacks a permit reviewer cares
    about.
    """
    ratio = stack.exit_velocity_ms / wind_ms
    if ratio >= 1.5:
        return 0.0
    return 2.0 * (ratio - 1.5) * stack.diameter_m


def plume_rise_m(stack: Stack, wind_ms: float) -> float:
    """Holland's formula for rise above the (downwash-corrected) stack top.

        dh = (vs*d/u) * (1.5 + 2.68e-3 * P * d * (Ts-Ta)/Ts)

    with P in millibars (1013 at sea level), d in m, vs and u in m/s.
    """
    pressure_mb = 1013.0
    momentum = stack.exit_velocity_ms * stack.diameter_m / wind_ms
    buoyancy = 2.68e-3 * pressure_mb * stack.diameter_m * (
        (stack.exit_temperature_k - stack.ambient_temperature_k) / stack.exit_temperature_k
    )
    # A stack-tip downwash can exceed the rise; the plume cannot start below the
    # stack base, and a negative rise added to a reduced h' would do exactly that.
    return max(momentum * (1.5 + buoyancy), 0.0)


def effective_stack_height_m(stack: Stack, wind_ms: float, *, urban: bool = False) -> float:
    corrected = max(stack.height_m + stack_tip_downwash_m(stack, wind_ms), 1.0)
    return corrected + plume_rise_m(stack, wind_ms)


def briggs_sigmas(distance_m: float, stability: str, *, urban: bool = False) -> tuple[float, float]:
    """(sigma_y, sigma_z) in metres from the Briggs coefficients.

    Below 100 m the fitted curves are extrapolated, which is where they are least
    trustworthy; the function still returns a value so a near-field receptor gets
    a number rather than a crash, and `screening_confidence` flags that region.
    """
    if distance_m <= 0:
        raise ValueError("distance_m must be > 0")
    table = _BRIGGS_URBAN if urban else _BRIGGS_OPEN
    ay, by, cy, az, bz, cz = table[stability]

    def curve(a: float, b: float, c: float) -> float:
        if b == 0.0:
            return a * distance_m
        return a * distance_m * (1.0 + b * distance_m) ** c

    return curve(ay, by, cy), curve(az, bz, cz)


def screening_confidence(distance_m: float) -> str:
    """How much the Briggs fit can be trusted at this distance."""
    if distance_m < 100:
        return "extrapolated below the fitted range"
    if distance_m > 10_000:
        return "extrapolated beyond the fitted range"
    return "within fitted range"


def ground_level_concentration(
    plume: PlumeState, distance_m: float, y_m: float = 0.0
) -> float:
    """Ground-level concentration at (x, y) in µg/m³.

        C = Q/(2 pi u sy sz) exp(-y^2/2sy^2) [reflection terms]

    The reflection terms are the infinite series of ground and lid images; when no
    mixing height is given only the ground pair survives, which is the open-terrain
    form. Q is g/s and u m/s, so C comes out in g/m³ and is scaled to µg/m³.
    """
    if distance_m <= 0:
        raise ValueError("distance_m must be > 0")

    u = wind_at_height(
        plume.wind_speed_10m_ms, plume.stack.height_m, plume.stability, urban=plume.urban
    )
    sy, sz = briggs_sigmas(distance_m, plume.stability, urban=plume.urban)
    if sy <= 0 or sz <= 0:
        raise ValueError("dispersion coefficients collapsed to zero")

    h_eff = effective_stack_height_m(plume.stack, u, urban=plume.urban)
    crosswind = math.exp(-(y_m**2) / (2.0 * sy**2))
    prefactor = plume.emission_rate_gs / (2.0 * math.pi * u * sy * sz)

    if plume.mixing_height_m is None:
        vertical = 2.0 * math.exp(-(h_eff**2) / (2.0 * sz**2))
    else:
        lid = plume.mixing_height_m
        if sz > 1.6 * lid:
            # Well-mixed layer: the image series has flattened into a uniform
            # profile and summing more terms gains nothing. The uniform-mixing
            # limit is C = Q/(sqrt(2pi) u sy L); expressed against `prefactor`
            # that is a vertical factor of sqrt(2pi)*sz/L.
            vertical = math.sqrt(2.0 * math.pi) * sz / lid
        else:
            vertical = 0.0
            for n in range(-4, 5):
                vertical += math.exp(-((h_eff - 2.0 * n * lid) ** 2) / (2.0 * sz**2))
                vertical += math.exp(-((h_eff + 2.0 * n * lid) ** 2) / (2.0 * sz**2))

    return prefactor * crosswind * vertical * 1e6  # g/m3 -> ug/m3


def centreline_concentration(plume: PlumeState, distance_m: float) -> float:
    """Concentration on the plume centreline at ground level, µg/m³."""
    return ground_level_concentration(plume, distance_m, 0.0)


def concentration_grid(
    plume: PlumeState, distances_m: tuple[float, ...], y_m: float = 0.0
) -> list[tuple[float, float, float]]:
    """(x, y, µg/m³) for each distance. Convenience wrapper for the CLI."""
    return [(x, y_m, ground_level_concentration(plume, x, y_m)) for x in distances_m]


def peak_downwind_distance(plume: PlumeState, max_distance_m: float = 10_000.0) -> float:
    """Distance where centreline ground-level concentration is highest.

    Scanned rather than solved: the maximum of the Briggs-convolved profile has no
    closed form, and a 5 m scan is far below the model's own uncertainty.
    """
    best_x, best_c = 10.0, -1.0
    x = 10.0
    while x <= max_distance_m:
        value = centreline_concentration(plume, x)
        if value > best_c:
            best_x, best_c = x, value
        x += 5.0
    return best_x


def stability_from_weather(
    wind_10m_ms: float, *, insolation: str | None = None, night_cloud_eighths: int | None = None
) -> str:
    """Pasquill class from surface wind and either daytime insolation or night cloud.

    `insolation` is 'strong', 'moderate' or 'slight'. At night, cloud cover of
    4/8 or more is 'thin' cloud (the weakly stable half of the table) and less
    than that is clear. Passing neither raises: guessing the class would make the
    whole dispersion answer unfalsifiable.
    """
    if insolation is None and night_cloud_eighths is None:
        raise ValueError("supply daytime insolation or night cloud cover")

    if insolation is not None:
        column = {"strong": 0, "moderate": 1, "slight": 2}.get(insolation)
        if column is None:
            raise ValueError(f"insolation must be strong/moderate/slight, got {insolation!r}")
        for upper, *classes in _PASQUILL_DAY:
            if wind_10m_ms < upper:
                return classes[column]
    else:
        column = 1 if (night_cloud_eighths or 0) >= 4 else 0
        for upper, *classes in _PASQUILL_NIGHT:
            if wind_10m_ms < upper:
                return classes[column]
    return "D"
