"""Geocoding, directions, weather, and the route plan they produce."""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from routing.cache import (
    GEOCODE_TTL,
    ROUTE_TTL,
    WEATHER_TTL,
    geocode_cache_key,
    recall,
    remember,
    route_cache_key,
    weather_cache_key,
)
from routing.constants import (
    FORECAST_DAYS,
    FORECAST_HOURS,
    HEIGIT_ACCOUNT_URL,
    METERS_PER_MILE,
    MILES_PER_DEGREE,
    OPEN_METEO_FORECAST_PATH,
    OPEN_METEO_GEOCODE_URL,
    ORS_AUTOCOMPLETE_PATH,
    ORS_DIRECTIONS_PATH,
    ORS_FREE_TIER_MAX_METERS,
    OSRM_BASE_URL,
    OSRM_DRIVING_PATH,
    SAMPLE_INTERVALS,
    VIA_OFFSETS_MILES,
    WEATHER_BATCH,
)
from routing.recommend import rank_routes, summarize_checkpoints
from routing.risk import RISK_SCORE, RiskLevel, classify_checkpoint
from routing.sampling import corridor_points, haversine_miles, sample_route

MISSING_KEY = (
    "Add OPENROUTESERVICE_API_KEY to the server environment. "
    f"A free key is available from {HEIGIT_ACCOUNT_URL}."
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


def _proxy_headers(token: str) -> dict[str, str]:
    if not token:
        return {}
    # workers.dev rejects the default Python client signature.
    return {
        "User-Agent": "Mozilla/5.0 (compatible; truck-router/1.0)",
        "X-Weather-Token": token,
    }


class OrsClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        http: httpx.Client,
        *,
        osrm_base_url: str = OSRM_BASE_URL,
        geocode_url: str = OPEN_METEO_GEOCODE_URL,
        proxy_token: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = _normalize_api_key(api_key)
        self.http = http
        self.osrm_base_url = osrm_base_url.rstrip("/")
        self.geocode_url = geocode_url.rstrip("/")
        self.proxy_token = proxy_token

    def autocomplete(self, text: str) -> list[Place]:
        self._require_key()
        key = geocode_cache_key(text)
        cached = recall(key)
        if cached is not None:
            return cached
        places = self._autocomplete(text)
        remember(key, places, GEOCODE_TTL)
        return places

    def _autocomplete(self, text: str) -> list[Place]:
        try:
            payload = _request(
                self.http,
                "GET",
                f"{self.base_url}{ORS_AUTOCOMPLETE_PATH}",
                service="geocode",
                params={"text": text, "size": 6, "api_key": self.api_key},
                headers=self._headers(),
            )
        except PlanningError as exc:
            if exc.status in {400, 404}:
                return []
            if exc.status in {401, 403}:
                return self._open_meteo_places(text)
            raise
        return _places_from_pelias(payload)

    def choose_routes(self, origin: Place, destination: Place) -> tuple[str, list[RawRoute]]:
        """Prefer three truck routes, and use car alternatives when HGV is short.

        A disallowed HeiGIT key, or a trip the free tier cannot accept, falls
        through to the public OSRM driving service.
        """
        self._require_key()
        key = route_cache_key(origin, destination)
        cached = recall(key)
        if cached is not None:
            return cached
        result = self._choose_routes(origin, destination)
        if result[1]:
            remember(key, result, ROUTE_TTL)
        return result

    def _choose_routes(self, origin: Place, destination: Place) -> tuple[str, list[RawRoute]]:
        straight_meters = haversine_miles(origin.lon, origin.lat, destination.lon, destination.lat)
        straight_meters *= METERS_PER_MILE
        if straight_meters > ORS_FREE_TIER_MAX_METERS:
            return self._public_routes(origin, destination, limited=True)
        limited = False
        try:
            return self._ors_routes(origin, destination)
        except PlanningError as exc:
            limited = _distance_limited(exc)
            if exc.status not in {401, 403} and not limited:
                raise
        return self._public_routes(origin, destination, limited=limited)

    def _public_routes(
        self,
        origin: Place,
        destination: Place,
        *,
        limited: bool,
    ) -> tuple[str, list[RawRoute]]:
        routes = self._osrm_routes(origin, destination)
        if not routes:
            raise PlanningError(
                "OpenRouteService disallowed this API key, and no public driving route was found.",
                502,
            )
        profile = "osrm-limit" if limited else "osrm"
        return profile, self._complete_with_vias(origin, destination, routes, profile)

    def _ors_routes(self, origin: Place, destination: Place) -> tuple[str, list[RawRoute]]:
        hgv = self._directions_or_empty("driving-hgv", origin, destination)
        if len(hgv) >= 3:
            return "driving-hgv", hgv[:3]
        car = self._directions_or_empty("driving-car", origin, destination)
        if len(car) >= 3 or len(car) > len(hgv):
            profile, routes = "driving-car", car
        elif hgv:
            profile, routes = "driving-hgv", hgv
        elif car:
            profile, routes = "driving-car", car
        else:
            raise PlanningError("No drivable route was found between those places.", 404)
        return profile, self._complete_with_vias(origin, destination, routes, profile)

    def _open_meteo_places(self, text: str) -> list[Place]:
        payload = _request(
            self.http,
            "GET",
            self.geocode_url,
            service="geocode",
            params={"name": text, "count": 6, "language": "en"},
            headers=_proxy_headers(self.proxy_token),
        )
        places: list[Place] = []
        for item in payload.get("results") or []:
            label = ", ".join(
                part
                for part in (item.get("name"), item.get("admin1"), item.get("country"))
                if part
            )
            try:
                lat = float(item["latitude"])
                lon = float(item["longitude"])
            except (KeyError, TypeError, ValueError):
                continue
            if label:
                places.append(Place(label=label, lat=lat, lon=lon))
        return _unique_places(places)

    def _complete_with_vias(
        self,
        origin: Place,
        destination: Place,
        routes: list[RawRoute],
        profile: str,
    ) -> list[RawRoute]:
        """Add a road on each side of the corridor until three options exist."""
        collected = list(routes)
        if len(collected) >= 3:
            return collected[:3]
        for via in _side_vias(origin, destination):
            collected = _unique_routes(collected + self._route_via(origin, destination, via, profile))
            if len(collected) >= 3:
                break
        return collected[:3]

    def _route_via(
        self,
        origin: Place,
        destination: Place,
        via: tuple[float, float],
        profile: str,
    ) -> list[RawRoute]:
        try:
            if profile.startswith("osrm"):
                return self._osrm_routes(origin, destination, via=via)
            return self.directions(profile, origin, destination, via=via)
        except PlanningError:
            return []

    def _osrm_routes(
        self,
        origin: Place,
        destination: Place,
        via: tuple[float, float] | None = None,
    ) -> list[RawRoute]:
        points = [f"{origin.lon},{origin.lat}"]
        if via is not None:
            points.append(f"{via[0]},{via[1]}")
        points.append(f"{destination.lon},{destination.lat}")
        path = ";".join(points)
        payload = _request(
            self.http,
            "GET",
            f"{self.osrm_base_url}{OSRM_DRIVING_PATH.format(path=path)}",
            service="routing",
            params={
                "overview": "full",
                "geometries": "geojson",
                "alternatives": "false" if via is not None else "2",
                "steps": "false",
            },
        )
        if payload.get("code") != "Ok":
            return []
        routes: list[RawRoute] = []
        for route in payload.get("routes") or []:
            coordinates = (route.get("geometry") or {}).get("coordinates") or []
            if len(coordinates) < 2:
                continue
            routes.append(
                RawRoute(
                    coordinates=coordinates,
                    distance_meters=float(route.get("distance") or 0),
                    duration_seconds=float(route.get("duration") or 0),
                )
            )
        return _unique_routes(routes)

    def directions(
        self,
        profile: str,
        origin: Place,
        destination: Place,
        via: tuple[float, float] | None = None,
    ) -> list[RawRoute]:
        coordinates = [[origin.lon, origin.lat]]
        if via is not None:
            coordinates.append([via[0], via[1]])
        coordinates.append([destination.lon, destination.lat])
        body: dict = {"coordinates": coordinates, "instructions": False}
        if via is None:
            body["alternative_routes"] = {
                "target_count": 2,
                "share_factor": 0.6,
                "weight_factor": 1.4,
            }
        payload = _request(
            self.http,
            "POST",
            f"{self.base_url}{ORS_DIRECTIONS_PATH.format(profile=profile)}",
            service="routing",
            params={"api_key": self.api_key},
            headers=self._headers(),
            json=body,
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
            if _distance_limited(exc):
                raise
            if exc.status in {400, 404}:
                return []
            raise

    def _require_key(self) -> None:
        if not self.api_key:
            raise PlanningError(MISSING_KEY, 503)

    def _headers(self) -> dict[str, str]:
        return {"Accept": "application/json, application/geo+json"}


class WeatherClient:
    def __init__(self, base_url: str, http: httpx.Client, proxy_token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.http = http
        self.proxy_token = proxy_token

    def hourly(self, points: list[tuple[float, float]]) -> list[ForecastSeries]:
        series: list[ForecastSeries | None] = [None] * len(points)
        missing: list[tuple[str, float, float]] = []
        indexes: dict[str, list[int]] = {}
        for index, (lat, lon) in enumerate(points):
            key = weather_cache_key(lat, lon)
            cached = recall(key)
            if cached is not None:
                series[index] = cached
                continue
            if key not in indexes:
                missing.append((key, lat, lon))
                indexes[key] = []
            indexes[key].append(index)
        for start in range(0, len(missing), WEATHER_BATCH):
            batch = missing[start : start + WEATHER_BATCH]
            payload = _request(
                self.http,
                "GET",
                f"{self.base_url}{OPEN_METEO_FORECAST_PATH}",
                service="weather",
                params={
                    "latitude": ",".join(f"{lat:.5f}" for _key, lat, _lon in batch),
                    "longitude": ",".join(f"{lon:.5f}" for _key, _lat, lon in batch),
                    "hourly": "wind_speed_10m,rain,showers,snowfall",
                    "wind_speed_unit": "mph",
                    "precipitation_unit": "inch",
                    "forecast_days": FORECAST_DAYS,
                    "timezone": "auto",
                },
                headers=_proxy_headers(self.proxy_token),
            )
            items = payload if isinstance(payload, list) else [payload]
            if len(items) != len(batch):
                raise PlanningError("Weather forecast did not cover every point.", 502)
            for (key, _lat, _lon), item in zip(batch, items):
                parsed = _parse_series(item)
                remember(key, parsed, WEATHER_TTL)
                for index in indexes[key]:
                    series[index] = parsed
        found = [item for item in series if item is not None]
        if len(found) != len(points):
            raise PlanningError("Weather forecast did not cover every point.", 502)
        return found


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
        raise PlanningError("The OpenRouteService API key was rejected.", response.status_code)
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
        upstream = _upstream_message(response)
        if service == "routing" and response.status_code == 400 and upstream:
            raise PlanningError(upstream, 400)
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


def _normalize_api_key(api_key: str) -> str:
    """Keep the base64 padding the HeiGIT playground sends with the key."""
    key = api_key.strip().strip('"').strip("'")
    if not key or key.endswith("="):
        return key
    return key + ("=" * ((4 - (len(key) % 4)) % 4))


def _distance_limited(exc: PlanningError) -> bool:
    text = exc.message.lower()
    return exc.status == 400 and ("100000" in exc.message or "configuration limits" in text)


def _upstream_message(response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return ""
    if not isinstance(payload, dict):
        return ""
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or "")
    if isinstance(error, str):
        return error
    return ""


def _places_from_pelias(payload: dict) -> list[Place]:
    places: list[Place] = []
    for feature in payload.get("features") or []:
        coordinates = (feature.get("geometry") or {}).get("coordinates") or []
        label = str((feature.get("properties") or {}).get("label") or "").strip()
        if not label or len(coordinates) < 2:
            continue
        places.append(Place(label=label, lon=float(coordinates[0]), lat=float(coordinates[1])))
    return _unique_places(places)


def _unique_places(places: list[Place]) -> list[Place]:
    """Drop repeats that share a label and the same map point."""
    seen: set[tuple[str, float, float]] = set()
    unique: list[Place] = []
    for place in places:
        key = (place.label, round(place.lat, 5), round(place.lon, 5))
        if key in seen:
            continue
        seen.add(key)
        unique.append(place)
    return unique


def _side_vias(origin: Place, destination: Place) -> list[tuple[float, float]]:
    """Points left and right of the straight line, nearest offsets first."""
    mid_lat = (origin.lat + destination.lat) / 2
    mid_lon = (origin.lon + destination.lon) / 2
    east = (destination.lon - origin.lon) * math.cos(math.radians(mid_lat)) * MILES_PER_DEGREE
    north = (destination.lat - origin.lat) * MILES_PER_DEGREE
    length = math.hypot(east, north)
    if length < 1:
        return []
    unit_east, unit_north = -north / length, east / length
    cosine = math.cos(math.radians(mid_lat)) or 1.0
    points: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()
    for miles in VIA_OFFSETS_MILES:
        offset = min(miles, max(4.0, length * 0.4))
        for sign in (1.0, -1.0):
            lat = mid_lat + (sign * offset * unit_north) / MILES_PER_DEGREE
            lon = mid_lon + (sign * offset * unit_east) / (MILES_PER_DEGREE * cosine)
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            key = (round(lon, 3), round(lat, 3))
            if key in seen:
                continue
            seen.add(key)
            points.append((lon, lat))
    return points


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
