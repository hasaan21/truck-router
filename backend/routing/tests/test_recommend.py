from types import SimpleNamespace

import pytest

from routing.recommend import rank_routes, summarize_checkpoints
from routing.risk import RiskLevel


def _route(name, segments, duration, distance=100):
    summary = summarize_checkpoints(
        [
            SimpleNamespace(risk=level, segment_miles=miles)
            for level, miles in segments
        ],
        distance,
        duration,
    )
    return SimpleNamespace(name=name, summary=summary)


def test_average_risk_is_weighted_by_miles():
    summary = summarize_checkpoints(
        [
            SimpleNamespace(risk=RiskLevel.SEVERE, segment_miles=10),
            SimpleNamespace(risk=RiskLevel.LOW, segment_miles=30),
        ],
        40,
        1800,
    )
    assert summary.severe_miles == 10
    assert summary.low_miles == 30
    assert summary.average_risk == pytest.approx((3 * 10) / 40)


def test_no_travel_loses_to_a_longer_severe_route():
    ranked = rank_routes(
        [
            _route("blocked", [(RiskLevel.NO_TRAVEL, 5), (RiskLevel.LOW, 95)], 1000),
            _route("stormy", [(RiskLevel.SEVERE, 40), (RiskLevel.LOW, 160)], 8000, 200),
        ]
    )
    assert [route.name for route in ranked] == ["stormy", "blocked"]


def test_fewer_severe_miles_outrank_fewer_high_miles():
    ranked = rank_routes(
        [
            _route("high", [(RiskLevel.HIGH, 80), (RiskLevel.LOW, 20)], 4000),
            _route("severe", [(RiskLevel.SEVERE, 5), (RiskLevel.LOW, 95)], 2000),
        ]
    )
    assert [route.name for route in ranked] == ["high", "severe"]


def test_fewer_high_miles_outrank_a_lower_average():
    ranked = rank_routes(
        [
            _route(
                "spiky",
                [(RiskLevel.HIGH, 10), (RiskLevel.LOW, 90)],
                3000,
            ),
            _route(
                "steady",
                [(RiskLevel.MODERATE, 40), (RiskLevel.LOW, 60)],
                3000,
            ),
        ]
    )
    assert [route.name for route in ranked] == ["steady", "spiky"]
    assert ranked[1].summary.average_risk < ranked[0].summary.average_risk


def test_lower_average_risk_then_shorter_time():
    ranked = rank_routes(
        [
            _route("slow-calm", [(RiskLevel.LOW, 50)], 9000),
            _route("mixed", [(RiskLevel.MODERATE, 10), (RiskLevel.LOW, 40)], 1000),
            _route("fast-calm", [(RiskLevel.LOW, 50)], 4000),
        ]
    )
    assert [route.name for route in ranked] == ["fast-calm", "slow-calm", "mixed"]


def test_exact_ties_keep_input_order():
    ranked = rank_routes(
        [
            _route("first", [(RiskLevel.HIGH, 8)], 1200),
            _route("second", [(RiskLevel.HIGH, 8)], 1200),
        ]
    )
    assert [route.name for route in ranked] == ["first", "second"]
