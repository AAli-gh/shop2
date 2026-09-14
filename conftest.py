import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _isolated_cache():
    """Rate-limit counters and cached site settings live in the cache; start every test clean."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _sms_outbox(settings):
    """Never write or send real SMS from tests; messages land in LocmemSmsBackend.outbox."""
    from apps.common.sms import LocmemSmsBackend

    settings.SMS_BACKEND = "apps.common.sms.LocmemSmsBackend"
    LocmemSmsBackend.outbox.clear()
    yield LocmemSmsBackend.outbox
