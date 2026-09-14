from datetime import timedelta

import pytest
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product
from apps.discounts.models import Coupon
from apps.orders.models import Order
from apps.orders.services import (
    EmptyCartError,
    InvalidCouponError,
    OutOfStockError,
    place_order,
)


@pytest.fixture
def user(db, django_user_model):
    return django_user_model.objects.create_user(email="buyer@example.com", password="x")


@pytest.fixture
def product(db):
    cat = Category.objects.create(name="cat", slug="cat")
    return Product.objects.create(category=cat, name="p", slug="p", price=100_000, stock=5)


@pytest.fixture
def cart_with_item(user, product):
    cart = Cart.objects.create(user=user)
    CartItem.objects.create(cart=cart, product=product, quantity=2)
    return cart


ADDRESS = {
    "full_name": "a", "phone": "09120000000", "province": "پ",
    "city": "ش", "postal_code": "1234567890", "address_line": "addr",
}


def test_place_order_happy_path(user, cart_with_item, product):
    order = place_order(user=user, cart=cart_with_item, address_data=ADDRESS)
    assert order.status == Order.Status.PENDING_PAYMENT
    assert order.items_subtotal == 200_000
    assert order.total == 200_000 + 50_000  # default flat shipping
    product.refresh_from_db()
    assert product.stock == 3
    assert cart_with_item.items.count() == 0
    assert order.items.first().unit_price == 100_000
    assert order.shipping_address.city == "ش"


def test_place_order_empty_cart(user, db):
    cart = Cart.objects.create(user=user)
    with pytest.raises(EmptyCartError):
        place_order(user=user, cart=cart, address_data=ADDRESS)


def test_place_order_out_of_stock_rolls_back(user, cart_with_item, product):
    product.stock = 1
    product.save()
    with pytest.raises(OutOfStockError):
        place_order(user=user, cart=cart_with_item, address_data=ADDRESS)
    cart_with_item.refresh_from_db()
    assert cart_with_item.items.count() == 1  # rolled back, cart intact


def test_place_order_price_snapshot(user, cart_with_item, product):
    product.price = 150_000
    product.save()
    order = place_order(user=user, cart=cart_with_item, address_data=ADDRESS)
    assert order.items.first().unit_price == 150_000
    assert order.items_subtotal == 300_000


def test_place_order_with_coupon(user, cart_with_item, product):
    Coupon.objects.create(
        code="SAVE10", kind=Coupon.Kind.PERCENT, value=10,
        valid_from=timezone.now() - timedelta(days=1),
        valid_to=timezone.now() + timedelta(days=1),
    )
    order = place_order(
        user=user, cart=cart_with_item, address_data=ADDRESS, coupon_code="SAVE10"
    )
    assert order.discount_amount == 20_000
    assert order.total == 200_000 - 20_000 + 50_000
    assert Coupon.objects.get(code="SAVE10").used_count == 1


def test_coupon_limit_exhausted_aborts_order(user, cart_with_item, product):
    Coupon.objects.create(
        code="LIMITED", kind=Coupon.Kind.PERCENT, value=10,
        valid_from=timezone.now() - timedelta(days=1),
        valid_to=timezone.now() + timedelta(days=1),
        usage_limit=1, used_count=1,
    )
    with pytest.raises(InvalidCouponError):
        place_order(user=user, cart=cart_with_item, address_data=ADDRESS, coupon_code="LIMITED")
    product.refresh_from_db()
    assert product.stock == 5
    assert cart_with_item.items.count() == 1


def test_free_shipping_threshold(user, cart_with_item):
    from apps.common.models import SiteSettings

    s = SiteSettings.load()
    s.free_shipping_threshold = 200_000
    s.save()
    order = place_order(user=user, cart=cart_with_item, address_data=ADDRESS)
    assert order.shipping_cost == 0
    assert order.total == 200_000


def test_free_shipping_threshold_uses_presubtotal(user, cart_with_item, product):
    """Threshold applies to pre-discount subtotal."""
    from apps.common.models import SiteSettings

    s = SiteSettings.load()
    s.free_shipping_threshold = 200_000
    s.save()
    Coupon.objects.create(
        code="BIG", kind=Coupon.Kind.FIXED, value=50_000,
        valid_from=timezone.now() - timedelta(days=1),
        valid_to=timezone.now() + timedelta(days=1),
    )
    order = place_order(user=user, cart=cart_with_item, address_data=ADDRESS, coupon_code="BIG")
    assert order.shipping_cost == 0
    assert order.total == 200_000 - 50_000 + 0
