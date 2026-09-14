from datetime import timedelta

import pytest
from django.utils import timezone

from apps.discounts.services import validate_coupon
from apps.discounts.models import Coupon


@pytest.fixture
def coupon(db):
    return Coupon.objects.create(
        code="TEST10",
        kind=Coupon.Kind.PERCENT,
        value=10,
        max_discount_amount=100_000,
        valid_from=timezone.now() - timedelta(days=1),
        valid_to=timezone.now() + timedelta(days=1),
        usage_limit=2,
    )


def test_valid_percent_coupon(coupon):
    result = validate_coupon(code="test10", subtotal=500_000)
    assert result.error is None
    assert result.discount_amount == 50_000


def test_percent_coupon_capped(coupon):
    result = validate_coupon(code="TEST10", subtotal=2_000_000)
    assert result.discount_amount == 100_000


def test_expired_coupon(coupon):
    coupon.valid_to = timezone.now() - timedelta(hours=1)
    coupon.save()
    assert validate_coupon(code="TEST10", subtotal=500_000).error == "expired"


def test_not_started_coupon(coupon):
    coupon.valid_from = timezone.now() + timedelta(hours=1)
    coupon.save()
    assert validate_coupon(code="TEST10", subtotal=500_000).error == "not_started"


def test_usage_limit_reached(coupon):
    coupon.used_count = coupon.usage_limit
    coupon.save()
    assert validate_coupon(code="TEST10", subtotal=500_000).error == "usage_limit_reached"


def test_min_order_not_met(coupon):
    coupon.min_order_amount = 1_000_000
    coupon.save()
    assert validate_coupon(code="TEST10", subtotal=500_000).error == "min_order_not_met"


def test_unknown_code(coupon):
    assert validate_coupon(code="NOPE", subtotal=500_000).error == "not_found"


def test_inactive_coupon(coupon):
    coupon.is_active = False
    coupon.save()
    assert validate_coupon(code="TEST10", subtotal=500_000).error == "inactive"


def test_fixed_coupon(db):
    Coupon.objects.create(
        code="FLAT50",
        kind=Coupon.Kind.FIXED,
        value=50_000,
        valid_from=timezone.now() - timedelta(days=1),
        valid_to=timezone.now() + timedelta(days=1),
    )
    result = validate_coupon(code="FLAT50", subtotal=30_000)
    assert result.discount_amount == 30_000
