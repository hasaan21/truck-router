from django.conf import settings
import httpx
from rest_framework.decorators import api_view
from rest_framework.response import Response

from routing.services import OrsClient, PlanningError, WeatherClient, build_plan


@api_view(["GET"])
def health(_request):
    return Response({"status": "ok"})


@api_view(["GET"])
def geocode(request):
    query = request.query_params.get("q", "").strip()
    if len(query) < 2:
        return Response([])
    try:
        with httpx.Client(timeout=20) as http:
            places = _ors(http).autocomplete(query)
    except PlanningError as exc:
        return Response({"detail": exc.message}, status=exc.status)
    return Response(
        [{"label": place.label, "lat": place.lat, "lon": place.lon} for place in places]
    )


@api_view(["POST"])
def plan(request):
    try:
        with httpx.Client(timeout=30) as http:
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
    )
