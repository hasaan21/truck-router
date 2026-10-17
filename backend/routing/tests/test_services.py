from datetime import datetime, timedelta, timezone

import pytest
from rest_framework.test import APIClient

from routing.sampling import corridor_points, sample_route
from routing.services import (
    ForecastSeries,
    OrsClient,
    Place,
    PlanningError,
    RawRoute,
    WeatherClient,
    build_plan,
)


CHICAGO = Place("Chicago, Illinois, USA", 41.88, -87.63)
DENVER = Place("Denver, Colorado, USA", 39.74, -104.99)


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


class FakeHttp:
    def __init__(self, responder):
        self.responder = responder

    def request(self, method, url, **kwargs):
        return self.responder(method, url, kwargs)


def _feature(coordinates, distance, duration):
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coordinates},
        "properties": {"summary": {"distance": distance, "duration": duration}},
    }


def _collection(features):
    return {"type": "FeatureCollection", "features": features}


def _line(start_lon, end_lon, lat=41.8):
    return [[start_lon, lat], [end_lon, lat]]


def test_truck_profile_falls_back_to_car_when_alternatives_are_short():
    first = _line(-87.7, -87.1, 41.9)
    second = _line(-87.7, -87.0, 42.0)
    third = _line(-87.7, -86.9, 42.1)

    def responder(_method, url, _kwargs):
        if "driving-hgv" in url:
            return FakeResponse(404, {"error": "no route"})
        assert "driving-car" in url
        return FakeResponse(
            200,
            _collection(
                [
                    _feature(first, 80_000, 4000),
                    _feature(second, 90_000, 4500),
                    _feature(third, 100_000, 5000),
                ]
            ),
        )

    profile, routes = OrsClient("https://api.heigit.org", "test-key", FakeHttp(responder)).choose_routes(
        CHICAGO, DENVER
    )
    assert profile == "driving-car"
    assert len(routes) == 3
    assert routes[0].distance_meters == 80_000


def test_three_truck_routes_skip_the_car_fallback():
    calls = []

    def responder(_method, url, _kwargs):
        calls.append(url)
        features = [
            _feature(_line(-87.7, -87.1, 41.8 + index / 10), 50_000, 3000)
            for index in range(3)
        ]
        return FakeResponse(200, _collection(features))

    profile, routes = OrsClient("https://api.heigit.org", "test-key", FakeHttp(responder)).choose_routes(
        CHICAGO, DENVER
    )
    assert profile == "driving-hgv"
    assert len(routes) == 3
    assert len(calls) == 1


def test_missing_key_is_reported_before_a_network_call():
    def responder(*_args):
        raise AssertionError("network should not be called")

    client = OrsClient("https://api.heigit.org", "", FakeHttp(responder))
    with pytest.raises(PlanningError) as exc:
        client.choose_routes(CHICAGO, DENVER)
    assert exc.value.status == 503
    assert "OPENROUTESERVICE_API_KEY" in exc.value.message


def test_autocomplete_reads_pelias_features():
    def responder(method, url, kwargs):
        assert method == "GET"
        assert url.endswith("/pelias/v1/autocomplete")
        assert kwargs["params"]["text"] == "den"
        assert kwargs["params"]["api_key"] == "test-key"
        return FakeResponse(
            200,
            {
                "features": [
                    {
                        "geometry": {"coordinates": [-104.99, 39.74]},
                        "properties": {"label": "Denver, Colorado, USA"},
                    }
                ]
            },
        )

    places = OrsClient("https://api.heigit.org", "test-key", FakeHttp(responder)).autocomplete("den")
    assert places == [Place("Denver, Colorado, USA", 39.74, -104.99)]


def test_autocomplete_drops_repeated_places():
    def responder(_method, _url, _kwargs):
        feature = {
            "geometry": {"coordinates": [124.33333, 7.88333]},
            "properties": {"label": "Tamparan, LS, Philippines"},
        }
        return FakeResponse(200, {"features": [feature, feature]})

    places = OrsClient("https://api.heigit.org", "test-key", FakeHttp(responder)).autocomplete("tam")
    assert places == [Place("Tamparan, LS, Philippines", 7.88333, 124.33333)]


def test_disallowed_pelias_key_falls_back_to_open_meteo():
    def responder(_method, url, kwargs):
        if "pelias" in url:
            return FakeResponse(403, {"error": "Access to this API has been disallowed"})
        assert "geocoding-api.open-meteo.com" in url
        assert kwargs["params"]["name"] == "Chicago"
        return FakeResponse(
            200,
            {
                "results": [
                    {
                        "name": "Chicago",
                        "admin1": "Illinois",
                        "country": "United States",
                        "latitude": 41.85,
                        "longitude": -87.65,
                    }
                ]
            },
        )

    places = OrsClient("https://api.heigit.org", "test-key", FakeHttp(responder)).autocomplete("Chicago")
    assert places == [Place("Chicago, Illinois, United States", 41.85, -87.65)]


def test_api_key_padding_matches_the_playground():
    client = OrsClient("https://api.heigit.org", "abc", FakeHttp(lambda *_args: None))
    assert client.api_key == "abc="


def test_long_trip_limit_falls_back_to_osrm():
    def responder(_method, url, _kwargs):
        if "openrouteservice" in url:
            return FakeResponse(
                400,
                {
                    "error": {
                        "code": 2004,
                        "message": "The approximated route distance must not be greater than 100000.0 meters.",
                    }
                },
            )
        return FakeResponse(
            200,
            {
                "code": "Ok",
                "routes": [
                    {
                        "distance": 500000,
                        "duration": 18000,
                        "geometry": {"coordinates": _line(-87.6, -104.9), "type": "LineString"},
                    }
                ],
            },
        )

    profile, routes = OrsClient("https://api.heigit.org", "test-key", FakeHttp(responder)).choose_routes(
        CHICAGO, DENVER
    )
    assert profile == "osrm-limit"
    assert routes[0].distance_meters == 500000
    def responder(method, url, _kwargs):
        if "openrouteservice" in url:
            return FakeResponse(403, {"error": "Access to this API has been disallowed"})
        assert method == "GET"
        assert "/route/v1/driving/" in url
        return FakeResponse(
            200,
            {
                "code": "Ok",
                "routes": [
                    {
                        "distance": 1609,
                        "duration": 120,
                        "geometry": {"coordinates": _line(-87.6, -87.4), "type": "LineString"},
                    },
                    {
                        "distance": 2000,
                        "duration": 150,
                        "geometry": {"coordinates": _line(-87.6, -87.3, 41.9), "type": "LineString"},
                    },
                ],
            },
        )

    profile, routes = OrsClient("https://api.heigit.org", "test-key", FakeHttp(responder)).choose_routes(
        CHICAGO, DENVER
    )
    assert profile == "osrm"
    assert len(routes) == 2
    assert routes[0].distance_meters == 1609


def test_short_alternative_list_gains_a_side_route():
    direct = _line(-87.6, -87.4)
    other = _line(-87.6, -87.3, 41.9)
    side = _line(-87.6, -87.2, 42.2)

    def responder(_method, url, kwargs):
        if "openrouteservice" in url:
            coordinates = kwargs["json"]["coordinates"]
            if len(coordinates) == 3:
                assert "alternative_routes" not in kwargs["json"]
                return FakeResponse(200, _collection([_feature(side, 120_000, 6000)]))
            return FakeResponse(
                200,
                _collection([_feature(direct, 80_000, 4000), _feature(other, 90_000, 4500)]),
            )
        return FakeResponse(500, {})

    profile, routes = OrsClient("https://api.heigit.org", "test-key", FakeHttp(responder)).choose_routes(
        CHICAGO, DENVER
    )
    assert profile == "driving-hgv"
    assert len(routes) == 3
    assert routes[2].distance_meters == 120_000


def test_weather_combines_rain_and_showers_in_local_time():
    def responder(_method, url, kwargs):
        assert url.endswith("/v1/forecast")
        assert kwargs["params"]["timezone"] == "auto"
        assert kwargs["params"]["wind_speed_unit"] == "mph"
        assert kwargs["params"]["precipitation_unit"] == "inch"
        return FakeResponse(
            200,
            {
                "utc_offset_seconds": -18000,
                "hourly": {
                    "time": ["2026-10-18T08:00", "2026-10-18T09:00"],
                    "wind_speed_10m": [10, None],
                    "rain": [0.2, 0.1],
                    "showers": [0.05, None],
                    "snowfall": [0, 1.5],
                },
            },
        )

    series = WeatherClient("https://api.open-meteo.com", FakeHttp(responder)).hourly([(41.8, -87.6)])
    assert series[0].times[0] == datetime(2026, 10, 18, 13, 0, tzinfo=timezone.utc)
    assert series[0].at(datetime(2026, 10, 18, 13, 30, tzinfo=timezone.utc)) == (10, 0.25, 0)
    wind, rain, snow = series[0].at(datetime(2026, 10, 18, 14, 0, tzinfo=timezone.utc))
    assert wind == 0
    assert rain == pytest.approx(0.1)
    assert snow == pytest.approx(1.5)


def test_plan_recommends_the_calmer_route_and_precomputes_48_hours():
    calm = _line(-104.9, -104.2, 39.7)
    blocked = _line(-104.9, -104.2, 39.9)
    departure = datetime(2026, 10, 18, 14, 0, tzinfo=timezone.utc)
    calm_samples = sample_route(calm, 25, departure, 5000)
    blocked_samples = sample_route(blocked, 25, departure, 3000)
    corridor = corridor_points([blocked, calm])

    class StubOrs:
        api_key = "test-key"

        def choose_routes(self, _origin, _destination):
            return "driving-hgv", [
                RawRoute(blocked, 70_000, 3000),
                RawRoute(calm, 80_000, 5000),
            ]

    class StubWeather:
        def hourly(self, points):
            assert len(points) == len(blocked_samples) + len(calm_samples) + len(corridor)
            start = departure - timedelta(hours=1)
            times = [start + timedelta(hours=hour) for hour in range(80)]
            series = []
            for index in range(len(points)):
                wind = 60 if index < len(blocked_samples) else 5
                series.append(ForecastSeries(times, [wind] * len(times), [0.0] * len(times), [0.0] * len(times)))
            return series

    payload = build_plan(
        {
            "origin": {"label": CHICAGO.label, "lat": CHICAGO.lat, "lon": CHICAGO.lon},
            "destination": {"label": DENVER.label, "lat": DENVER.lat, "lon": DENVER.lon},
            "departure": "2026-10-18T09:00:00",
            "timezone": "America/Chicago",
            "load_weight_lb": 35000,
            "sample_interval_miles": 25,
        },
        StubOrs(),
        StubWeather(),
    )
    assert payload["recommended_route_id"] == "route-0"
    assert payload["routes"][0]["summary"]["no_travel_miles"] == 0
    assert payload["routes"][1]["summary"]["no_travel_miles"] > 0
    assert payload["routes"][1]["checkpoints"][0]["risk"] == "no_travel"
    assert payload["routes"][0]["checkpoints"][0]["wind_mph"] == 5
    assert len(payload["heatmap"]["points"]) == len(corridor)
    assert len(payload["heatmap"]["points"][0]["risks"]) == 48
    assert payload["departure"] == "2026-10-18T14:00:00+00:00"


def test_corridor_offsets_leave_the_road_and_stay_capped():
    short = corridor_points([[[-87.6, 41.8], [-87.0, 41.8]]])
    assert len(short) > 1
    assert max(lat for lat, _lon in short) > 41.9

    long = corridor_points([[[0.0, 0.0], [30.0, 0.0]]])
    assert len(long) == 400


def test_plan_endpoint_validates_before_calling_services():
    client = APIClient()
    response = client.post(
        "/api/plan/",
        {
            "origin": {"label": "Chicago", "lat": 41.88, "lon": -87.63},
            "destination": {"label": "Denver", "lat": 39.74, "lon": -104.99},
            "departure": "2026-10-18T09:00:00",
            "timezone": "America/Chicago",
            "load_weight_lb": 20000,
            "sample_interval_miles": 15,
        },
        format="json",
    )
    assert response.status_code == 400
    assert "sample interval" in response.json()["detail"]


def test_plan_endpoint_reports_a_missing_key(settings):
    settings.OPENROUTESERVICE_API_KEY = ""
    client = APIClient()
    response = client.post(
        "/api/plan/",
        {
            "origin": {"label": "Chicago", "lat": 41.88, "lon": -87.63},
            "destination": {"label": "Denver", "lat": 39.74, "lon": -104.99},
            "departure": "2026-10-18T09:00:00",
            "timezone": "America/Chicago",
            "load_weight_lb": 20000,
            "sample_interval_miles": 50,
        },
        format="json",
    )
    assert response.status_code == 503
    assert "OPENROUTESERVICE_API_KEY" in response.json()["detail"]


def test_geocode_endpoint_returns_nothing_for_a_short_query():
    response = APIClient().get("/api/geocode/", {"q": "d"})
    assert response.status_code == 200
    assert response.json() == []
