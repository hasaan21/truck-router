"""Turn checkpoint risk into route totals and a recommended order."""

from dataclasses import dataclass
from typing import Protocol

from routing.risk import RISK_SCORE, RiskLevel


class ScoredCheckpoint(Protocol):
    risk: RiskLevel
    segment_miles: float


@dataclass(frozen=True)
class RouteSummary:
    distance_miles: float
    duration_seconds: float
    no_travel_miles: float
    severe_miles: float
    high_miles: float
    moderate_miles: float
    low_miles: float
    average_risk: float


class RankableRoute(Protocol):
    summary: RouteSummary


def summarize_checkpoints(
    checkpoints: list[ScoredCheckpoint],
    distance_miles: float,
    duration_seconds: float,
) -> RouteSummary:
    """Mile-weighted risk. Average uses low=0 through no_travel=4."""
    miles_by_level = {level: 0.0 for level in RiskLevel}
    weighted = 0.0
    owned = 0.0
    for checkpoint in checkpoints:
        miles = float(checkpoint.segment_miles)
        miles_by_level[checkpoint.risk] += miles
        weighted += RISK_SCORE[checkpoint.risk] * miles
        owned += miles
    return RouteSummary(
        distance_miles=float(distance_miles),
        duration_seconds=float(duration_seconds),
        no_travel_miles=miles_by_level[RiskLevel.NO_TRAVEL],
        severe_miles=miles_by_level[RiskLevel.SEVERE],
        high_miles=miles_by_level[RiskLevel.HIGH],
        moderate_miles=miles_by_level[RiskLevel.MODERATE],
        low_miles=miles_by_level[RiskLevel.LOW],
        average_risk=(weighted / owned) if owned else 0.0,
    )


def rank_routes(routes: list[RankableRoute]) -> list[RankableRoute]:
    """Prefer no-travel, then severe, then high, then average risk, then time.

    No-travel miles rank first because that outcome is stricter than severe.
    Equal routes keep their incoming order.
    """
    return sorted(
        routes,
        key=lambda route: (
            route.summary.no_travel_miles,
            route.summary.severe_miles,
            route.summary.high_miles,
            route.summary.average_risk,
            route.summary.duration_seconds,
        ),
    )
