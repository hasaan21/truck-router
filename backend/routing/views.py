from django.conf import settings
import httpx
from rest_framework.decorators import api_view
from rest_framework.response import Response

from routing.services import OrsClient, PlanningError, WeatherClient, build_plan

_http: httpx.Client | None = None


def _http_client() -> httpx.Client:
    """Reuse one client so later calls keep the existing TLS connection."""
    global _http
    if _http is None:
        _http = httpx.Client(timeout=30)
    return _http


@api_view(["GET"])
def health(_request):
    return Response({"status": "ok"})


@api_view(["GET"])
def geocode(request):
    query = request.query_params.get("q", "").strip()
    if len(query) < 2:
        return Response([])
    try:
        places = _ors(_http_client()).autocomplete(query)
    except PlanningError as exc:
        return Response({"detail": exc.message}, status=exc.status)
    return Response(
        [{"label": place.label, "lat": place.lat, "lon": place.lon} for place in places]
    )


@api_view(["POST"])
def plan(request):
    try:
        http = _http_client()
        payload = build_plan(
            request.data,
            _ors(http),
            WeatherClient(settings.OPEN_METEO_BASE_URL, http),
        )
    except PlanningError as exc:
        return Response({"detail": exc.message}, status=exc.status)
    return Response(payload)


def _ors(http: httpx.Client) -> OrsClient:
    return OrsClient(
        settings.OPENROUTESERVICE_BASE_URL,
        settings.OPENROUTESERVICE_API_KEY,
        http,
        osrm_base_url=settings.OSRM_BASE_URL,
        geocode_url=settings.OPEN_METEO_GEOCODE_URL,
    )
