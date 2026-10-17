"""Place weather checkpoints along a route geometry."""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

EARTH_RADIUS_MILES = 3958.7613


@dataclass(frozen=True)
class CheckpointSample:
    lon: float
    lat: float
    mile: float
    eta: datetime
    segment_miles: float


def haversine_miles(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(min(1.0, math.sqrt(a)))


def sample_route(
    coordinates: list[list[float]],
    interval_miles: float,
    departure: datetime,
    duration_seconds: float,
) -> list[CheckpointSample]:
    """Sample the line at the interval, always including the destination.

    Each checkpoint owns the miles until the next one. The destination owns none.
    Arrival time follows distance along the drawn line and the route duration.
    """
    if len(coordinates) < 2:
        raise ValueError("A route needs at least two coordinates.")
    if interval_miles <= 0:
        raise ValueError("Sample interval must be positive.")

    cumulative = _cumulative_miles(coordinates)
    total = cumulative[-1]
    miles = _sample_miles(total, interval_miles)
    samples: list[CheckpointSample] = []
    for index, mile in enumerate(miles):
        lon, lat = _point_at_mile(coordinates, cumulative, mile)
        fraction = 0.0 if total == 0 else mile / total
        next_mile = miles[index + 1] if index + 1 < len(miles) else mile
        samples.append(
            CheckpointSample(
                lon=lon,
                lat=lat,
                mile=mile,
                eta=departure + timedelta(seconds=float(duration_seconds) * fraction),
                segment_miles=next_mile - mile,
            )
        )
    return samples


def _sample_miles(total: float, interval: float) -> list[float]:
    if total <= 0:
        return [0.0]
    miles = []
    mile = 0.0
    while mile < total - 1e-6:
        miles.append(mile)
        mile += interval
    miles.append(total)
    return miles


def _cumulative_miles(coordinates: list[list[float]]) -> list[float]:
    cumulative = [0.0]
    for start, end in zip(coordinates, coordinates[1:]):
        step = haversine_miles(start[0], start[1], end[0], end[1])
        cumulative.append(cumulative[-1] + step)
    return cumulative


def _point_at_mile(
    coordinates: list[list[float]],
    cumulative: list[float],
    mile: float,
) -> tuple[float, float]:
    if mile <= 0:
        return coordinates[0][0], coordinates[0][1]
    if mile >= cumulative[-1]:
        return coordinates[-1][0], coordinates[-1][1]
    for index in range(len(cumulative) - 1):
        start = cumulative[index]
        end = cumulative[index + 1]
        if mile > end and index < len(cumulative) - 2:
            continue
        span = end - start
        if span == 0:
            return coordinates[index][0], coordinates[index][1]
        ratio = (mile - start) / span
        lon = coordinates[index][0] + ratio * (coordinates[index + 1][0] - coordinates[index][0])
        lat = coordinates[index][1] + ratio * (coordinates[index + 1][1] - coordinates[index][1])
        return lon, lat
    return coordinates[-1][0], coordinates[-1][1]
