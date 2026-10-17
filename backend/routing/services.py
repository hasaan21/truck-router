"""Geocoding, directions, weather, and the route plan they produce."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from routing.recommend import rank_routes, summarize_checkpoints
from routing.risk import RISK_SCORE, RiskLevel, classify_checkpoint
from routing.sampling import corridor_points, haversine_miles, sample_route

METERS_PER_MILE = 1609.344
FORECAST_DAYS = 7
FORECAST_HOURS = 48
WEATHER_BATCH = 50
SAMPLE_INTERVALS = {10, 25, 50}
MISSING_KEY = (
    "Add OPENROUTESERVICE_API_KEY to the server environment. "
    "A free key is available from https://account.heigit.org."
)


class PlanningError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass(frozen=True)
class Place:
    label: str
    lat: float
    lon: float


@dataclass(frozen=True)
class RawRoute:
    coordinates: list[list[float]]
    distance_meters: float
    duration_seconds: float


@dataclass(frozen=True)
class ForecastSeries:
    times: list[datetime]
    wind_mph: list[float]
    rain_in_hr: list[float]
    snow_in_hr: list[float]

    def at(self, moment: datetime) -> tuple[float, float, float]:
        moment = moment.astimezone(timezone.utc)
        if not self.times:
            raise PlanningError("Weather forecast was empty.", 502)
        if moment < self.times[0] or moment >= self.times[-1] + timedelta(hours=1):
            raise PlanningError(
                "The trip needs weather outside the 7-day forecast. "
                "Choose an earlier departure.",
                400,
            )
        index = _hour_index(self.times, moment)
        return self.wind_mph[index], self.rain_in_hr[index], self.snow_in_hr[index]


@dataclass
class ScoredCheckpoint:
    lon: float
    lat: float
    mile: float
    eta: datetime
    segment_miles: float
    wind_mph: float
    rain_in_hr: float
    snow_in_hr: float
    wind_risk: RiskLevel
    rain_risk: RiskLevel
    snow_risk: RiskLevel
    risk: RiskLevel


class OrsClient:
    def __init__(self, base_url: str, api_key: str, http: httpx.Client):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.http = http

    def autocomplete(self, text: str) -> list[Place]:
        self._require_key()
        try:
            payload = _request(
                self.http,
                "GET",
                f"{self.base_url}/pelias/v1/autocomplete",
                service="geocode",
                params={"text": text, "size": 6},
                headers=self._headers(),
            )
        except PlanningError as exc:
            if exc.status in {400, 404}:
                return []
            raise
        places: list[Place] = []
        for feature in payload.get("features") or []:
            coordinates = (feature.get("geometry") or {}).get("coordinates") or []
            label = str((feature.get("properties") or {}).get("label") or "").strip()
            if not label or len(coordinates) < 2:
                continue
            places.append(
                Place(label=label, lon=float(coordinates[0]), lat=float(coordinates[1]))
            )
        return places

    def choose_routes(self, origin: Place, destination: Place) -> tuple[str, list[RawRoute]]:
        """Prefer three truck routes, and use car alternatives when HGV is short."""
        self._require_key()
        hgv = self._directions_or_empty("driving-hgv", origin, destination)
        if len(hgv) >= 3:
            return "driving-hgv", hgv[:3]
        car = self._directions_or_empty("driving-car", origin, destination)
        if len(car) > len(hgv):
            return "driving-car", car[:3]
        if hgv:
            return "driving-hgv", hgv
        if car:
            return "driving-car", car
        raise PlanningError("No drivable route was found between those places.", 404)

    def directions(self, profile: str, origin: Place, destination: Place) -> list[RawRoute]:
        payload = _request(
            self.http,
            "POST",
            f"{self.base_url}/openrouteservice/v2/directions/{profile}/geojson",
            service="routing",
            headers=self._headers(),
            json={
                "coordinates": [
                    [origin.lon, origin.lat],
                    [destination.lon, destination.lat],
                ],
                "alternative_routes": {
                    "target_count": 2,
                    "share_factor": 0.6,
                    "weight_factor": 1.4,
                },
                "instructions": False,
            },
        )
        routes: list[RawRoute] = []
        for feature in payload.get("features") or []:
            coordinates = (feature.get("geometry") or {}).get("coordinates") or []
            summary = (feature.get("properties") or {}).get("summary") or {}
            if len(coordinates) < 2:
                continue
            routes.append(
                RawRoute(
                    coordinates=coordinates,
                    distance_meters=float(summary.get("distance") or 0),
                    duration_seconds=float(summary.get("duration") or 0),
                )
            )
        return _unique_routes(routes)

    def _directions_or_empty(
        self,
        profile: str,
        origin: Place,
        destination: Place,
    ) -> list[RawRoute]:
        try:
            return self.directions(profile, origin, destination)
        except PlanningError as exc:
            if exc.status in {400, 404}:
                return []
            raise

    def _require_key(self) -> None:
        if not self.api_key:
            raise PlanningError(MISSING_KEY, 503)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json, application/geo+json",
        }


class WeatherClient:
    def __init__(self, base_url: str, http: httpx.Client):
        self.base_url = base_url.rstrip("/")
        self.http = http

    def hourly(self, points: list[tuple[float, float]]) -> list[ForecastSeries]:
        series: list[ForecastSeries] = []
        for start in range(0, len(points), WEATHER_BATCH):
            batch = points[start : start + WEATHER_BATCH]
            payload = _request(
                self.http,
                "GET",
                f"{self.base_url}/v1/forecast",
                service="weather",
                params={
                    "latitude": ",".join(f"{lat:.5f}" for lat, _lon in batch),
                    "longitude": ",".join(f"{lon:.5f}" for _lat, lon in batch),
                    "hourly": "wind_speed_10m,rain,showers,snowfall",
                    "wind_speed_unit": "mph",
                    "precipitation_unit": "inch",
                    "forecast_days": FORECAST_DAYS,
                    "timezone": "auto",
                },
            )
            items = payload if isinstance(payload, list) else [payload]
            if len(items) != len(batch):
                raise PlanningError("Weather forecast did not cover every point.", 502)
            series.extend(_parse_series(item) for item in items)
        return series


def build_plan(body: object, ors: OrsClient, weather: WeatherClient) -> dict:
    if not isinstance(body, dict):
        raise PlanningError("Request body must be a JSON object.")
    origin = _place(body.get("origin"), "origin")
    destination = _place(body.get("destination"), "destination")
    if haversine_miles(origin.lon, origin.lat, destination.lon, destination.lat) < 1:
        raise PlanningError("Origin and destination need to be at least a mile apart.")
    departure = _departure(body.get("departure"), body.get("timezone"))
    load = _load(body.get("load_weight_lb"))
    interval = _interval(body.get("sample_interval_miles"))

    profile, raw_routes = ors.choose_routes(origin, destination)
    sampled = [
        (raw, sample_route(raw.coordinates, interval, departure, raw.duration_seconds))
        for raw in raw_routes
    ]
    corridor = corridor_points([raw.coordinates for raw, _samples in sampled])
    points: list[tuple[float, float]] = []
    for _raw, samples in sampled:
        points.extend((sample.lat, sample.lon) for sample in samples)
    corridor_at = len(points)
    points.extend(corridor)
    forecasts = weather.hourly(points)
    if len(forecasts) != len(points):
        raise PlanningError("Weather forecast did not cover every point.", 502)

    planned = []
    cursor = 0
    for raw, samples in sampled:
        scored: list[ScoredCheckpoint] = []
        geometry_miles = samples[-1].mile if samples else 0.0
        distance_miles = raw.distance_meters / METERS_PER_MILE
        if distance_miles <= 0:
            distance_miles = geometry_miles
        scale = (distance_miles / geometry_miles) if geometry_miles else 1.0
        for sample in samples:
            wind, rain, snow = forecasts[cursor].at(sample.eta)
            cursor += 1
            levels = classify_checkpoint(wind, rain, snow, load)
            scored.append(
                ScoredCheckpoint(
                    lon=sample.lon,
                    lat=sample.lat,
                    mile=sample.mile * scale,
                    eta=sample.eta,
                    segment_miles=sample.segment_miles * scale,
                    wind_mph=wind,
                    rain_in_hr=rain,
                    snow_in_hr=snow,
                    wind_risk=levels["wind_risk"],
                    rain_risk=levels["rain_risk"],
                    snow_risk=levels["snow_risk"],
                    risk=levels["risk"],
                )
            )
        summary = summarize_checkpoints(scored, distance_miles, raw.duration_seconds)
        planned.append(
            SimpleNamespace(
                profile=profile,
                coordinates=raw.coordinates,
                checkpoints=scored,
                summary=summary,
            )
        )

    ranked = rank_routes(planned)
    routes = [_serialize_route(index, route) for index, route in enumerate(ranked)]
    heatmap = []
    for index, (lat, lon) in enumerate(corridor):
        series = forecasts[corridor_at + index]
        risks = []
        for hour in range(FORECAST_HOURS):
            wind, rain, snow = series.at(departure + timedelta(hours=hour))
            level = classify_checkpoint(wind, rain, snow, load)["risk"]
            risks.append(RISK_SCORE[level])
        heatmap.append({"lat": round(lat, 5), "lon": round(lon, 5), "risks": risks})

    return {
        "recommended_route_id": routes[0]["id"] if routes else None,
        "profile": profile,
        "departure": _iso(departure),
        "timezone": body.get("timezone") or "UTC",
        "load_weight_lb": load,
        "sample_interval_miles": interval,
        "origin": {"label": origin.label, "lat": origin.lat, "lon": origin.lon},
        "destination": {
            "label": destination.label,
            "lat": destination.lat,
            "lon": destination.lon,
        },
        "routes": routes,
        "heatmap": {
            "hours": FORECAST_HOURS,
            "origin_time": _iso(departure),
            "points": heatmap,
        },
    }


def _request(http: httpx.Client, method: str, url: str, *, service: str, **kwargs):
    try:
        response = http.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        raise PlanningError(f"{_service_label(service)} could not be reached.", 502) from exc
    if response.status_code in {401, 403}:
        raise PlanningError("The OpenRouteService API key was rejected.", 502)
    if response.status_code == 429:
        raise PlanningError(
            f"{_service_label(service)} rate limit was reached. Try again shortly.",
            503,
        )
    if response.status_code >= 500:
        raise PlanningError(
            f"{_service_label(service)} returned an error. Try again shortly.",
            502,
        )
    if response.status_code >= 400:
        message = {
            "routing": "No drivable route was found between those places.",
            "geocode": "Place search failed. Try a different name.",
            "weather": "The weather service rejected the forecast request.",
        }[service]
        raise PlanningError(message, response.status_code)
    try:
        return response.json()
    except ValueError as exc:
        raise PlanningError(f"{_service_label(service)} returned an unreadable response.", 502) from exc


def _parse_series(item: dict) -> ForecastSeries:
    hourly = item.get("hourly") or {}
    stamps = hourly.get("time") or []
    offset = timedelta(seconds=int(item.get("utc_offset_seconds") or 0))
    zone = timezone(offset)
    times = [
        datetime.fromisoformat(stamp).replace(tzinfo=zone).astimezone(timezone.utc)
        for stamp in stamps
    ]
    count = len(times)
    wind = _numbers(hourly.get("wind_speed_10m"), count)
    rain = _numbers(hourly.get("rain"), count)
    showers = _numbers(hourly.get("showers"), count)
    snow = _numbers(hourly.get("snowfall"), count)
    return ForecastSeries(
        times=times,
        wind_mph=wind,
        rain_in_hr=[left + right for left, right in zip(rain, showers)],
        snow_in_hr=snow,
    )


def _numbers(values, count: int) -> list[float]:
    cleaned = [0.0 if value is None else max(0.0, float(value)) for value in values or []]
    if len(cleaned) != count:
        raise PlanningError("Weather forecast was incomplete.", 502)
    return cleaned


def _hour_index(times: list[datetime], moment: datetime) -> int:
    # Latest forecast hour at or before the arrival. Precipitation is the
    # preceding hour, and wind is the value at that hour.
    lo = 0
    hi = len(times)
    while lo < hi:
        mid = (lo + hi) // 2
        if times[mid] <= moment:
            lo = mid + 1
        else:
            hi = mid
    return max(0, lo - 1)


def _unique_routes(routes: list[RawRoute]) -> list[RawRoute]:
    unique: list[RawRoute] = []
    seen: set[tuple] = set()
    for route in routes:
        key = tuple((round(lon, 4), round(lat, 4)) for lon, lat in route.coordinates)
        if key in seen:
            continue
        seen.add(key)
        unique.append(route)
    return unique


def _place(value: object, name: str) -> Place:
    if not isinstance(value, dict):
        raise PlanningError(f"Choose an {name} from the suggestions.")
    label = str(value.get("label") or "").strip()
    try:
        lat = float(value["lat"])
        lon = float(value["lon"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PlanningError(f"Choose an {name} from the suggestions.") from exc
    if not label:
        raise PlanningError(f"Choose an {name} from the suggestions.")
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise PlanningError(f"The {name} coordinates are not valid.")
    return Place(label=label, lat=lat, lon=lon)


def _load(value: object) -> float:
    try:
        load = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise PlanningError("Enter a load weight in pounds.") from exc
    if load < 0 or load > 200_000:
        raise PlanningError("Load weight must be between 0 and 200,000 pounds.")
    return load


def _interval(value: object) -> int:
    try:
        interval = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise PlanningError("Choose a sample interval of 10, 25, or 50 miles.") from exc
    if interval not in SAMPLE_INTERVALS:
        raise PlanningError("Choose a sample interval of 10, 25, or 50 miles.")
    return interval


def _departure(value: object, tz_name: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise PlanningError("Choose a departure date and time.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise PlanningError("Departure time is not a valid date.") from exc
    if parsed.tzinfo is None:
        if not isinstance(tz_name, str) or not tz_name.strip():
            raise PlanningError("A timezone is required with the departure time.")
        try:
            parsed = parsed.replace(tzinfo=ZoneInfo(tz_name.strip()))
        except ZoneInfoNotFoundError as exc:
            raise PlanningError("The departure timezone is not recognized.") from exc
    return parsed.astimezone(timezone.utc)


def _serialize_route(index: int, route) -> dict:
    summary = route.summary
    return {
        "id": f"route-{index}",
        "profile": route.profile,
        "summary": {
            "distance_miles": round(summary.distance_miles, 2),
            "duration_seconds": round(summary.duration_seconds),
            "no_travel_miles": round(summary.no_travel_miles, 2),
            "severe_miles": round(summary.severe_miles, 2),
            "high_miles": round(summary.high_miles, 2),
            "moderate_miles": round(summary.moderate_miles, 2),
            "low_miles": round(summary.low_miles, 2),
            "average_risk": round(summary.average_risk, 3),
        },
        "geometry": {"type": "LineString", "coordinates": route.coordinates},
        "checkpoints": [_serialize_checkpoint(point) for point in route.checkpoints],
    }


def _serialize_checkpoint(point: ScoredCheckpoint) -> dict:
    return {
        "lat": point.lat,
        "lon": point.lon,
        "mile": round(point.mile, 2),
        "eta": _iso(point.eta),
        "wind_mph": round(point.wind_mph, 1),
        "rain_in_hr": round(point.rain_in_hr, 3),
        "snow_in_hr": round(point.snow_in_hr, 3),
        "wind_risk": point.wind_risk.value,
        "rain_risk": point.rain_risk.value,
        "snow_risk": point.snow_risk.value,
        "risk": point.risk.value,
        "segment_miles": round(point.segment_miles, 2),
    }


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _service_label(service: str) -> str:
    return {
        "routing": "OpenRouteService",
        "geocode": "Place search",
        "weather": "The weather service",
    }[service]
