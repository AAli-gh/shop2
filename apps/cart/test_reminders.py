from datetime import timedelta

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.utils import timezone

from apps.cart import services as cart_services
from apps.cart.models import Cart, CartItem
from apps.cart.reminders import remind_abandoned_carts
from apps.catalog.models import Category, Product
from apps.common.sms import LocmemSmsBackend
from apps.orders.models import Order


@pytest.fixture
def product(db):
    category = Category.objects.create(name="c", slug="c")
    return Product.objects.create(category=category, name="همزن", slug="mixer", price=2_000_000, stock=5)


@pytest.fixture
def customer(django_user_model):
    return django_user_model.objects.create_user(phone="09121234567", phone_verified=True)


def _idle_cart(user, product, hours):
    cart = Cart.objects.create(user=user)
    CartItem.objects.create(cart=cart, product=product, quantity=1)
    Cart.objects.filter(pk=cart.pk).update(updated_at=timezone.now() - timedelta(hours=hours))
    return cart


def _texts():
    return [m["text"] for m in LocmemSmsBackend.outbox if m["phone"] == "09121234567"]


def test_an_idle_cart_gets_one_reminder(product, customer):
    cart = _idle_cart(customer, product, hours=4)

    assert remind_abandoned_carts() == 1
    assert len(_texts()) == 1 and "/cart/" in _texts()[0]
    assert Cart.objects.get(pk=cart.pk).reminded_at is not None

    assert remind_abandoned_carts() == 0


@pytest.mark.parametrize("hours", [1, 72])
def test_recent_and_stale_carts_are_left_alone(product, customer, hours):
    _idle_cart(customer, product, hours=hours)
    assert remind_abandoned_carts() == 0


def test_only_verified_mobiles_are_texted(product, django_user_model):
    unverified = django_user_model.objects.create_user(phone="09120000000", phone_verified=False)
    _idle_cart(unverified, product, hours=4)
    assert remind_abandoned_carts() == 0


def test_no_reminder_after_the_customer_ordered(product, customer):
    _idle_cart(customer, product, hours=4)
    Order.objects.create(order_number="SH-TEST0001", user=customer, total=2_000_000)
    assert remind_abandoned_carts() == 0


def test_a_cart_changed_after_its_reminder_can_be_reminded_again(product, customer):
    cart = _idle_cart(customer, product, hours=4)
    start = timezone.now()
    remind_abandoned_carts(now=start)

    Cart.objects.filter(pk=cart.pk).update(updated_at=start + timedelta(hours=1))

    assert remind_abandoned_carts(now=start + timedelta(hours=2)) == 0  # not idle long enough yet
    assert remind_abandoned_carts(now=start + timedelta(hours=5)) == 1


def test_cart_changes_record_activity(product, customer):
    cart = _idle_cart(customer, product, hours=10)
    old = Cart.objects.get(pk=cart.pk).updated_at

    class Request:
        user = customer
        session = SessionStore()

    cart_services.add_to_cart(Request(), product_id=product.pk)

    assert Cart.objects.get(pk=cart.pk).updated_at > old
