import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _isolated_cache():
    """Rate-limit counters and cached site settings live in the cache; start every test clean."""
    cache.clear()
    yield
    cache.clear()
