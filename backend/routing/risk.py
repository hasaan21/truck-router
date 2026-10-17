"""Weather and load risk levels for a single checkpoint."""

from enum import Enum


class RiskLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    SEVERE = "severe"
    NO_TRAVEL = "no_travel"


RISK_SCORE = {
    RiskLevel.LOW: 0,
    RiskLevel.MODERATE: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.SEVERE: 3,
    RiskLevel.NO_TRAVEL: 4,
}

# Shared band edges belong to the higher level. The published ranges meet
# at 0.25 in/hr of rain and at 1.0 and 2.0 in/hr of snow.
_RAIN_BANDS = (
    (0.10, RiskLevel.LOW),
    (0.25, RiskLevel.MODERATE),
    (0.50, RiskLevel.HIGH),
    (1.00, RiskLevel.SEVERE),
)
_SNOW_BANDS = (
    (0.5, RiskLevel.LOW),
    (1.0, RiskLevel.MODERATE),
    (2.0, RiskLevel.HIGH),
    (3.0, RiskLevel.SEVERE),
)


def classify_wind(mph: float, load_weight_lb: float) -> RiskLevel:
    """Classify sustained wind, then apply the load overrides."""
    speed = max(0.0, float(mph))
    load = max(0.0, float(load_weight_lb))
    if speed >= 55:
        return RiskLevel.NO_TRAVEL
    if speed >= 45:
        if load > 30_000:
            return RiskLevel.NO_TRAVEL
        return RiskLevel.SEVERE
    if speed >= 35:
        if load > 40_000:
            return RiskLevel.SEVERE
        return RiskLevel.HIGH
    if speed >= 25:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def classify_rain(inches_per_hour: float) -> RiskLevel:
    return _classify_upper_bound(max(0.0, float(inches_per_hour)), _RAIN_BANDS)


def classify_snow(inches_per_hour: float) -> RiskLevel:
    return _classify_upper_bound(max(0.0, float(inches_per_hour)), _SNOW_BANDS)


def classify_checkpoint(
    wind_mph: float,
    rain_in_hr: float,
    snow_in_hr: float,
    load_weight_lb: float,
) -> dict[str, RiskLevel]:
    """Return each hazard level and the worst of the three."""
    wind = classify_wind(wind_mph, load_weight_lb)
    rain = classify_rain(rain_in_hr)
    snow = classify_snow(snow_in_hr)
    return {
        "wind_risk": wind,
        "rain_risk": rain,
        "snow_risk": snow,
        "risk": max((wind, rain, snow), key=lambda level: RISK_SCORE[level]),
    }


def _classify_upper_bound(
    value: float,
    bands: tuple[tuple[float, RiskLevel], ...],
) -> RiskLevel:
    for limit, level in bands:
        if value < limit or (level is RiskLevel.SEVERE and value == limit):
            return level
    return RiskLevel.NO_TRAVEL
