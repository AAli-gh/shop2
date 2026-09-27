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


# ---------------------------------------------------------------- per-customer limits

def _order_with(user, coupon=None, status="paid"):
    from apps.orders.models import Order

    return Order.objects.create(
        order_number=f"SH-{Order.objects.count() + 1:08d}", user=user, status=status,
        items_subtotal=500_000, total=500_000, coupon=coupon,
    )


@pytest.fixture
def buyer(django_user_model):
    return django_user_model.objects.create_user(email="buyer@example.com", password="x")


def test_once_per_customer(coupon, buyer):
    coupon.per_user_limit = 1
    coupon.usage_limit = None
    coupon.save()
    assert validate_coupon(code="TEST10", subtotal=500_000, user=buyer).error is None

    _order_with(buyer, coupon)
    assert validate_coupon(code="TEST10", subtotal=500_000, user=buyer).error == "per_user_limit_reached"


def test_cancelled_order_gives_the_use_back(coupon, buyer):
    coupon.per_user_limit = 1
    coupon.save()
    _order_with(buyer, coupon, status="cancelled")
    assert validate_coupon(code="TEST10", subtotal=500_000, user=buyer).error is None


def test_first_order_only(coupon, buyer):
    coupon.first_order_only = True
    coupon.save()
    _order_with(buyer, status="cancelled")  # a cancelled order isn't a purchase
    assert validate_coupon(code="TEST10", subtotal=500_000, user=buyer).error is None

    _order_with(buyer)
    assert validate_coupon(code="TEST10", subtotal=500_000, user=buyer).error == "first_order_only"


def test_customer_rules_need_a_signed_in_buyer(coupon):
    from django.contrib.auth.models import AnonymousUser

    coupon.per_user_limit = 1
    coupon.save()
    assert validate_coupon(code="TEST10", subtotal=500_000).error == "login_required"
    assert validate_coupon(code="TEST10", subtotal=500_000, user=AnonymousUser()).error == "login_required"


def test_placing_a_second_order_with_a_used_up_code_is_refused(coupon, buyer):
    from apps.cart.models import Cart, CartItem
    from apps.catalog.models import Category, Product
    from apps.orders.services import InvalidCouponError, place_order

    coupon.per_user_limit = 1
    coupon.usage_limit = None
    coupon.save()
    product = Product.objects.create(category=Category.objects.create(name="c", slug="c"), name="p", slug="p",
                                     price=500_000, stock=5)
    address = {"full_name": "a", "phone": "09120000000", "province": "p", "city": "c",
               "postal_code": "1234567890", "address_line": "x"}
    cart = Cart.objects.create(user=buyer)
    CartItem.objects.create(cart=cart, product=product, quantity=1)
    assert place_order(user=buyer, cart=cart, address_data=address, coupon_code="TEST10").coupon == coupon

    CartItem.objects.create(cart=cart, product=product, quantity=1)
    with pytest.raises(InvalidCouponError):
        place_order(user=buyer, cart=cart, address_data=address, coupon_code="TEST10")
