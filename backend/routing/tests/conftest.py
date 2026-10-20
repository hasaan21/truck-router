import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear_route_cache():
    cache.clear()
    yield
    cache.clear()
