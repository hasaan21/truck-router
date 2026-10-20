"""Process-local TTLs for geocode, routes, and weather."""

from django.core.cache import cache

GEOCODE_TTL = 60 * 60 * 24
ROUTE_TTL = 60 * 60 * 12
WEATHER_TTL = 60 * 30


def geocode_cache_key(text: str) -> str:
    return f"geocode:{text.strip().casefold()}"


def route_cache_key(origin, destination) -> str:
    return (
        "routes:"
        f"{origin.lat:.4f},{origin.lon:.4f}:"
        f"{destination.lat:.4f},{destination.lon:.4f}"
    )


def weather_cache_key(lat: float, lon: float) -> str:
    return f"weather:{lat:.5f},{lon:.5f}"


def recall(key: str):
    return cache.get(key)


def remember(key: str, value, ttl: int) -> None:
    cache.set(key, value, ttl)
