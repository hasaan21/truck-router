"""Place weather checkpoints and corridor samples along a route geometry."""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

EARTH_RADIUS_MILES = 3958.7613
CORRIDOR_INTERVAL_MILES = 15
CORRIDOR_OFFSETS_MILES = (0, 10, -10, 20, -20)
MAX_CORRIDOR_POINTS = 400
_CORRIDOR_GRID_DEGREES = 0.05


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


def corridor_points(routes: list[list[list[float]]]) -> list[tuple[float, float]]:
    """Sample each route and step sideways so the forecast covers the corridor.

    Nearby samples collapse onto a coarse grid, and the result is capped so
    the forecast stays one payload the map can recolor without another request.
    """
    found: dict[tuple[int, int], tuple[float, float]] = {}
    anchor = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for coordinates in routes:
        if len(coordinates) < 2:
            continue
        samples = sample_route(coordinates, CORRIDOR_INTERVAL_MILES, anchor, 0)
        for index, sample in enumerate(samples):
            bearing = _bearing_at(samples, index)
            for offset in CORRIDOR_OFFSETS_MILES:
                if offset == 0:
                    lat, lon = sample.lat, sample.lon
                else:
                    side = bearing + (90 if offset > 0 else -90)
                    lat, lon = destination_point(sample.lat, sample.lon, side, abs(offset))
                key = (
                    round(lat / _CORRIDOR_GRID_DEGREES),
                    round(lon / _CORRIDOR_GRID_DEGREES),
                )
                found.setdefault(key, (lat, lon))
    points = list(found.values())
    if len(points) <= MAX_CORRIDOR_POINTS:
        return points
    step = len(points) / MAX_CORRIDOR_POINTS
    return [
        points[min(len(points) - 1, int(index * step))]
        for index in range(MAX_CORRIDOR_POINTS)
    ]


def destination_point(
    lat: float,
    lon: float,
    bearing_deg: float,
    miles: float,
) -> tuple[float, float]:
    if miles == 0:
        return lat, lon
    delta = miles / EARTH_RADIUS_MILES
    theta = math.radians(bearing_deg)
    phi1 = math.radians(lat)
    lambda1 = math.radians(lon)
    phi2 = math.asin(
        math.sin(phi1) * math.cos(delta)
        + math.cos(phi1) * math.sin(delta) * math.cos(theta)
    )
    lambda2 = lambda1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(phi1),
        math.cos(delta) - math.sin(phi1) * math.sin(phi2),
    )
    lon2 = (math.degrees(lambda2) + 540) % 360 - 180
    return math.degrees(phi2), lon2


def initial_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_lambda = math.radians(lon2 - lon1)
    x = math.sin(d_lambda) * math.cos(phi2)
    y = (
        math.cos(phi1) * math.sin(phi2)
        - math.sin(phi1) * math.cos(phi2) * math.cos(d_lambda)
    )
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _bearing_at(samples: list[CheckpointSample], index: int) -> float:
    if index < len(samples) - 1:
        current = samples[index]
        nxt = samples[index + 1]
        return initial_bearing(current.lat, current.lon, nxt.lat, nxt.lon)
    if index > 0:
        previous = samples[index - 1]
        current = samples[index]
        return initial_bearing(previous.lat, previous.lon, current.lat, current.lon)
    return 0.0
