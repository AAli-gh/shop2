from datetime import date, timedelta

import pytest
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product
from apps.common.sms import LocmemSmsBackend
from apps.orders.models import Order
from apps.orders.review_requests import request_reviews
from apps.orders.services import place_order, transition_status
from apps.payments.services import mark_paid
from apps.reviews.models import Review

ADDRESS = {
    "full_name": "مریم احمدی", "phone": "09121234567", "province": "تهران",
    "city": "تهران", "postal_code": "1234567890", "address_line": "خیابان آزادی",
}
TRACK_URL = "/orders/track/"


@pytest.fixture
def product(db):
    category = Category.objects.create(name="یخچال", slug="fridge")
    return Product.objects.create(category=category, name="یخچال ساید", slug="side", price=50_000_000, stock=5)


@pytest.fixture
def customer(django_user_model):
    return django_user_model.objects.create_user(email="buyer@example.com", password="x")


@pytest.fixture
def order(product, customer):
    cart = Cart.objects.create(user=customer)
    CartItem.objects.create(cart=cart, product=product, quantity=1)
    return place_order(user=customer, cart=cart, address_data=ADDRESS)


def deliver(order, days_ago=6):
    mark_paid(order=order, ref="REF-1")
    for status in (Order.Status.PROCESSING, Order.Status.SHIPPED, Order.Status.DELIVERED):
        transition_status(order=Order.objects.get(pk=order.pk), new_status=status)
    Order.objects.filter(pk=order.pk).update(delivered_at=timezone.now() - timedelta(days=days_ago))
    return Order.objects.get(pk=order.pk)


# ---------------------------------------------------------------- tracking without signing in

def test_the_order_is_found_by_its_number_and_mobile(client, order):
    page = client.post(TRACK_URL, {"order_number": order.order_number, "phone": "۰۹۱۲۱۲۳۴۵۶۷"}).content.decode()

    assert order.order_number in page
    assert "یخچال ساید" in page
    assert "در انتظار پرداخت" in page


def test_a_wrong_mobile_or_number_reveals_nothing(client, order):
    wrong_phone = client.post(TRACK_URL, {"order_number": order.order_number, "phone": "09120000000"}).content.decode()
    wrong_number = client.post(TRACK_URL, {"order_number": "SH-NOPE", "phone": "09121234567"}).content.decode()

    for page in (wrong_phone, wrong_number):
        assert "پیدا نشد" in page
        assert "یخچال ساید" not in page


def test_the_page_shows_progress_serial_and_tracking_code(client, order):
    delivered = deliver(order)
    Order.objects.filter(pk=delivered.pk).update(tracking_code="TRK-99")
    item = delivered.items.first()
    item.serial_numbers = "SN-12345"
    item.warranty_ends_at = date(2027, 3, 1)
    item.save()

    page = client.post(TRACK_URL, {"order_number": delivered.order_number, "phone": "09121234567"}).content.decode()

    assert "تحویل شد" in page and "TRK-99" in page
    assert "SN-12345" in page and "گارانتی تا" in page


def test_the_footer_links_to_tracking(client, db):
    assert TRACK_URL in client.get("/").content.decode()


def test_serial_and_warranty_are_on_the_invoice(client, order, customer):
    item = order.items.first()
    item.serial_numbers = "SN-12345"
    item.warranty_ends_at = date(2027, 3, 1)
    item.save()
    client.force_login(customer)

    invoice = client.get(f"/orders/{order.order_number}/invoice/").content.decode()

    assert "SN-12345" in invoice and "گارانتی تا" in invoice


@pytest.mark.django_db
def test_staff_can_type_the_serial_in_the_admin(admin_client, order):
    page = admin_client.get(f"/admin/orders/order/{order.pk}/change/").content.decode()
    assert "serial_numbers" in page
    assert admin_client.get("/admin/orders/order/?q=SN-12345").status_code == 200


# ---------------------------------------------------------------- review requests

def test_the_customer_is_asked_once_a_few_days_after_delivery(order, mailoutbox):
    delivered = deliver(order, days_ago=6)

    assert request_reviews() == 1
    assert [m.to for m in mailoutbox][-1] == ["buyer@example.com"]
    assert "یخچال ساید" in mailoutbox[-1].subject
    assert Order.objects.get(pk=delivered.pk).review_requested_at is not None

    assert request_reviews() == 0


@pytest.mark.parametrize("days_ago", [2, 40])
def test_too_soon_or_too_late_orders_are_skipped(order, days_ago, mailoutbox):
    deliver(order, days_ago=days_ago)
    assert request_reviews() == 0


def test_undelivered_orders_are_never_asked(order):
    mark_paid(order=order, ref="REF-1")
    assert request_reviews() == 0


def test_a_customer_who_already_reviewed_is_left_alone(order, product, customer):
    delivered = deliver(order)
    Review.objects.create(product=product, user=customer, rating=5, body="عالی بود")

    assert request_reviews() == 0
    assert Order.objects.get(pk=delivered.pk).review_requested_at is not None  # nothing left to ask


def test_phone_customers_get_a_text_with_its_own_event(product, django_user_model):
    customer = django_user_model.objects.create_user(phone="09121234567", phone_verified=True)
    cart = Cart.objects.create(user=customer)
    CartItem.objects.create(cart=cart, product=product, quantity=1)
    deliver(place_order(user=customer, cart=cart, address_data=ADDRESS))

    assert request_reviews() == 1

    message = [m for m in LocmemSmsBackend.outbox if m.get("event") == "review_request"][-1]
    assert message["params"] == {"PRODUCT": "یخچال ساید"}
    assert "/product/side/" in message["text"]
