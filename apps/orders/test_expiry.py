from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product
from apps.discounts.models import Coupon
from apps.orders.models import Order
from apps.orders.services import expire_unpaid_orders, place_order
from apps.payments.models import Payment
from apps.payments.services import mark_paid, start_payment

ADDRESS = {
    "full_name": "a", "phone": "09120000000", "province": "پ",
    "city": "ش", "postal_code": "1234567890", "address_line": "addr",
}

pytestmark = pytest.mark.usefixtures("payment_windows")


@pytest.fixture
def payment_windows(settings):
    settings.ORDER_PAYMENT_TIMEOUT_MINUTES = 30
    settings.ORDER_PAYMENT_GRACE_MINUTES = 15


@pytest.fixture
def user(db, django_user_model):
    return django_user_model.objects.create_user(email="late@example.com", password="x")


@pytest.fixture
def product(db):
    cat = Category.objects.create(name="c", slug="c")
    return Product.objects.create(category=cat, name="p", slug="p", price=100_000, stock=10)


def make_order(user, product, age_minutes, **kwargs):
    cart, _ = Cart.objects.get_or_create(user=user)  # one cart per user; placing an order empties it
    CartItem.objects.create(cart=cart, product=product, quantity=2)
    order = place_order(user=user, cart=cart, address_data=ADDRESS, **kwargs)
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(minutes=age_minutes))
    return order


def test_only_stale_unpaid_orders_expire(user, product):
    Coupon.objects.create(
        code="LATE", kind=Coupon.Kind.PERCENT, value=10,
        valid_from=timezone.now() - timedelta(days=1), valid_to=timezone.now() + timedelta(days=1),
    )
    stale = make_order(user, product, age_minutes=45, coupon_code="LATE")
    fresh = make_order(user, product, age_minutes=5)
    paid = make_order(user, product, age_minutes=45)
    mark_paid(order=paid, ref="REF")

    assert expire_unpaid_orders() == [stale.order_number]

    statuses = dict(Order.objects.values_list("order_number", "status"))
    assert statuses == {
        stale.order_number: Order.Status.CANCELLED,
        fresh.order_number: Order.Status.PENDING_PAYMENT,
        paid.order_number: Order.Status.PAID,
    }
    product.refresh_from_db()
    assert product.stock == 10 - 2 - 2  # stale order's units are back on sale
    assert Coupon.objects.get(code="LATE").used_count == 0


def test_order_with_a_payment_in_progress_is_left_alone(user, product):
    order = make_order(user, product, age_minutes=45)
    start_payment(order=order)  # customer is at the bank right now

    assert expire_unpaid_orders() == []

    Payment.objects.update(created_at=timezone.now() - timedelta(minutes=20))
    assert expire_unpaid_orders() == [order.order_number]


def test_expiry_notifies_the_customer(user, product, mailoutbox):
    make_order(user, product, age_minutes=45)
    before = len(mailoutbox)
    expire_unpaid_orders()
    assert any(user.email in message.to for message in mailoutbox[before:])


def test_command_dry_run_changes_nothing(user, product):
    order = make_order(user, product, age_minutes=45)

    out = StringIO()
    call_command("expire_unpaid_orders", "--dry-run", stdout=out)
    assert order.order_number in out.getvalue()
    order.refresh_from_db()
    assert order.status == Order.Status.PENDING_PAYMENT

    out = StringIO()
    call_command("expire_unpaid_orders", stdout=out)
    assert "expired 1 order" in out.getvalue()
    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED


def test_command_minutes_option_overrides_setting(user, product):
    order = make_order(user, product, age_minutes=10)
    call_command("expire_unpaid_orders", "--minutes", "60", stdout=StringIO())
    order.refresh_from_db()
    assert order.status == Order.Status.PENDING_PAYMENT
    call_command("expire_unpaid_orders", "--minutes", "5", stdout=StringIO())
    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
