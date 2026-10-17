import pytest

from routing.risk import RiskLevel, classify_checkpoint, classify_rain, classify_snow, classify_wind

WIND_CASES = [
    (0, 0, RiskLevel.LOW),
    (24.9, 80_000, RiskLevel.LOW),
    (25, 0, RiskLevel.MODERATE),
    (34, 80_000, RiskLevel.MODERATE),
    (34.9, 0, RiskLevel.MODERATE),
    (35, 0, RiskLevel.HIGH),
    (44, 40_000, RiskLevel.HIGH),
    (44.9, 30_000, RiskLevel.HIGH),
    (45, 0, RiskLevel.SEVERE),
    (54, 30_000, RiskLevel.SEVERE),
    (54.9, 0, RiskLevel.SEVERE),
    (55, 0, RiskLevel.NO_TRAVEL),
    (70, 0, RiskLevel.NO_TRAVEL),
    (35, 40_001, RiskLevel.SEVERE),
    (44.9, 40_001, RiskLevel.SEVERE),
    (45, 30_001, RiskLevel.NO_TRAVEL),
    (54.9, 30_001, RiskLevel.NO_TRAVEL),
    (55, 1, RiskLevel.NO_TRAVEL),
]


@pytest.mark.parametrize(("mph", "load", "expected"), WIND_CASES)
def test_wind_and_load_bands(mph, load, expected):
    assert classify_wind(mph, load) is expected


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (0, RiskLevel.LOW),
        (0.099, RiskLevel.LOW),
        (0.10, RiskLevel.MODERATE),
        (0.249, RiskLevel.MODERATE),
        (0.25, RiskLevel.HIGH),
        (0.499, RiskLevel.HIGH),
        (0.50, RiskLevel.SEVERE),
        (1.00, RiskLevel.SEVERE),
        (1.001, RiskLevel.NO_TRAVEL),
    ],
)
def test_rain_bands(amount, expected):
    assert classify_rain(amount) is expected


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (0, RiskLevel.LOW),
        (0.49, RiskLevel.LOW),
        (0.5, RiskLevel.MODERATE),
        (0.99, RiskLevel.MODERATE),
        (1.0, RiskLevel.HIGH),
        (1.99, RiskLevel.HIGH),
        (2.0, RiskLevel.SEVERE),
        (3.0, RiskLevel.SEVERE),
        (3.01, RiskLevel.NO_TRAVEL),
    ],
)
def test_snow_bands(amount, expected):
    assert classify_snow(amount) is expected


def test_checkpoint_uses_the_worst_hazard():
    result = classify_checkpoint(
        wind_mph=10,
        rain_in_hr=0.6,
        snow_in_hr=0.2,
        load_weight_lb=10_000,
    )
    assert result["wind_risk"] is RiskLevel.LOW
    assert result["rain_risk"] is RiskLevel.SEVERE
    assert result["snow_risk"] is RiskLevel.LOW
    assert result["risk"] is RiskLevel.SEVERE


def test_load_override_is_applied_before_the_worst_hazard():
    result = classify_checkpoint(
        wind_mph=50,
        rain_in_hr=0,
        snow_in_hr=0,
        load_weight_lb=30_001,
    )
    assert result["wind_risk"] is RiskLevel.NO_TRAVEL
    assert result["risk"] is RiskLevel.NO_TRAVEL


def test_negative_inputs_are_treated_as_zero():
    assert classify_wind(-5, -10) is RiskLevel.LOW
    assert classify_rain(-1) is RiskLevel.LOW
    assert classify_snow(-1) is RiskLevel.LOW
