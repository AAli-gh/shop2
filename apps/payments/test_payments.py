import json

import pytest
from django.core.management import call_command
from django.test import override_settings

from apps.accounts.models import Address
from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product
from apps.orders.models import Order
from apps.orders.services import cancel_pending_order, place_order
from apps.payments.gateways import MockGateway, ZarinPalGateway
from apps.payments.models import Payment
from apps.payments.services import PaymentError, complete_payment, start_payment

ADDRESS = {
    "full_name": "a", "phone": "09120000000", "province": "پ",
    "city": "ش", "postal_code": "1234567890", "address_line": "addr",
}


class RecordingGateway(MockGateway):
    """Mock gateway that counts how often the bank is asked to verify."""

    verify_calls = 0

    def verify(self, payment, **callback_params):
        RecordingGateway.verify_calls += 1
        return super().verify(payment, **callback_params)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeRequests:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        return self.responses.pop(0)


@pytest.fixture
def user(db, django_user_model):
    return django_user_model.objects.create_user(email="payer@example.com", password="x")


@pytest.fixture
def product(db):
    cat = Category.objects.create(name="c", slug="c")
    return Product.objects.create(category=cat, name="p", slug="p", price=100_000, stock=5)


@pytest.fixture
def order(user, product):
    cart = Cart.objects.create(user=user)
    CartItem.objects.create(cart=cart, product=product, quantity=1)
    return place_order(user=user, cart=cart, address_data=ADDRESS)


# ---------------------------------------------------------------- bug 1: missing migration + broken flow

@pytest.mark.django_db
def test_every_model_change_has_a_migration():
    # regression: the payments app shipped without a migration, so the Payment table never existed
    call_command("makemigrations", "--check", "--dry-run", verbosity=0)


def test_online_checkout_pays_through_the_gateway(client, user, product):
    cart = Cart.objects.create(user=user)
    CartItem.objects.create(cart=cart, product=product, quantity=1)
    address = Address.objects.create(user=user, **ADDRESS)
    client.force_login(user)

    resp = client.post("/checkout/place/", {"address_id": address.pk})
    order = Order.objects.get(user=user)
    assert resp.status_code == 302
    assert resp.url == f"/checkout/pay/{order.order_number}/"

    assert client.get(resp.url).status_code == 200
    payment = order.payments.get()
    assert payment.status == Payment.Status.CREATED

    resp = client.post(f"/checkout/pay/{order.order_number}/", {"outcome": "success"})
    assert resp.url == f"/orders/{order.order_number}/success/"
    order.refresh_from_db()
    payment.refresh_from_db()
    assert order.status == Order.Status.PAID
    assert payment.status == Payment.Status.VERIFIED
    assert order.payment_ref == payment.ref_id


def test_failed_payment_is_recorded_and_retry_starts_a_new_one(order):
    payment = start_payment(order=order)
    with pytest.raises(PaymentError):
        complete_payment(payment=payment, outcome="fail")

    payment.refresh_from_db()
    order.refresh_from_db()
    assert payment.status == Payment.Status.FAILED  # used to be rolled back with the exception
    assert order.status == Order.Status.PENDING_PAYMENT
    assert start_payment(order=order).pk != payment.pk


@override_settings(PAYMENT_GATEWAY="apps.payments.test_payments.RecordingGateway")
def test_payment_for_a_cancelled_order_is_never_verified(order):
    RecordingGateway.verify_calls = 0
    payment = start_payment(order=order)
    cancel_pending_order(order=order)  # e.g. expired while the customer was at the bank

    with pytest.raises(PaymentError):
        complete_payment(payment=payment)

    payment.refresh_from_db()
    order.refresh_from_db()
    assert RecordingGateway.verify_calls == 0
    assert payment.status == Payment.Status.FAILED
    assert order.status == Order.Status.CANCELLED


def test_mock_pay_page_is_disabled_with_a_real_gateway(client, user, order):
    client.force_login(user)
    with override_settings(PAYMENT_GATEWAY="apps.payments.gateways.ZarinPalGateway"):
        resp = client.post(f"/checkout/pay/{order.order_number}/", {"outcome": "success"})
    assert resp.status_code == 404
    order.refresh_from_db()
    assert order.status == Order.Status.PENDING_PAYMENT


# ---------------------------------------------------------------- bug 4: ZarinPal configuration

def test_zarinpal_settings_are_defined():
    from django.conf import settings

    assert set(settings.ZARINPAL) == {"MERCHANT_ID", "SANDBOX"}


@override_settings(ZARINPAL={"MERCHANT_ID": "", "SANDBOX": True})
def test_zarinpal_refuses_to_start_without_merchant_id(order):
    with pytest.raises(RuntimeError):
        ZarinPalGateway().create(order)


@override_settings(ZARINPAL={"MERCHANT_ID": "m-123", "SANDBOX": True}, SITE_URL="https://shop.example")
def test_zarinpal_create_sends_rial_amount_and_callback(order, monkeypatch):
    fake = FakeRequests(FakeResponse({"data": {"authority": "A0001", "code": 100}, "errors": []}))
    monkeypatch.setattr(ZarinPalGateway, "_client", lambda self: fake)

    intent = ZarinPalGateway().create(order)

    url, payload = fake.calls[0]
    assert url == "https://sandbox.zarinpal.com/pg/v4/payment/request.json"
    assert payload["merchant_id"] == "m-123"
    assert payload["amount"] == order.total * 10  # Toman -> Rial
    assert payload["callback_url"] == f"https://shop.example/payments/callback/{order.order_number}/"
    assert intent.result.success
    assert intent.redirect_url == "https://sandbox.zarinpal.com/pg/StartPay/A0001"


@override_settings(ZARINPAL={"MERCHANT_ID": "m-123", "SANDBOX": False})
def test_zarinpal_verify_success_and_failure(order, monkeypatch):
    payment = Payment.objects.create(order=order, provider="zarinpal", amount_toman=order.total, authority="A0001")
    fake = FakeRequests(
        FakeResponse({"data": {"code": 100, "ref_id": 987, "fee": 25_000, "card_pan": "6037****1234"}, "errors": []}),
        FakeResponse({"data": {}, "errors": {"code": -51, "message": "failed"}}),
    )
    monkeypatch.setattr(ZarinPalGateway, "_client", lambda self: fake)
    gateway = ZarinPalGateway()

    ok = gateway.verify(payment, Status="OK")
    assert fake.calls[0][0] == "https://api.zarinpal.com/pg/v4/payment/verify.json"
    assert fake.calls[0][1]["amount"] == order.total * 10
    assert ok.success and ok.ref == "987" and ok.fee_toman == 2_500

    assert gateway.verify(payment, Status="OK").success is False
    assert gateway.verify(payment, Status="NOK").success is False  # user abandoned at the bank
    assert len(fake.calls) == 2  # NOK never reaches the verify endpoint


class DownRequests:
    """ZarinPal unreachable: every call times out."""

    def post(self, url, json=None, timeout=None):
        import requests

        raise requests.Timeout("read timed out")


class HtmlResponse(FakeResponse):
    def json(self):
        raise ValueError("Expecting value")  # an HTML error page instead of JSON


@override_settings(PAYMENT_GATEWAY="apps.payments.gateways.ZarinPalGateway",
                   ZARINPAL={"MERCHANT_ID": "m-123", "SANDBOX": True})
def test_zarinpal_outage_while_verifying_leaves_the_payment_open(order, monkeypatch):
    payment = Payment.objects.create(order=order, provider="zarinpal", amount_toman=order.total, authority="A0001")
    monkeypatch.setattr(ZarinPalGateway, "_client", lambda self: DownRequests())

    with pytest.raises(PaymentError):
        complete_payment(payment=payment, Status="OK")

    payment.refresh_from_db()
    order.refresh_from_db()
    # not FAILED: the bank may have taken the money, so the next visit must verify again
    assert payment.status == Payment.Status.CREATED
    assert order.status == Order.Status.PENDING_PAYMENT

    ok = FakeRequests(FakeResponse({"data": {"code": 101, "ref_id": 5}, "errors": []}))
    monkeypatch.setattr(ZarinPalGateway, "_client", lambda self: ok)
    complete_payment(payment=payment, Status="OK")
    order.refresh_from_db()
    assert order.status == Order.Status.PAID


@override_settings(PAYMENT_GATEWAY="apps.payments.gateways.ZarinPalGateway",
                   ZARINPAL={"MERCHANT_ID": "m-123", "SANDBOX": True})
def test_zarinpal_error_page_on_start_shows_a_message(client, user, order, monkeypatch):
    fake = FakeRequests(HtmlResponse({}, status_code=502))
    monkeypatch.setattr(ZarinPalGateway, "_client", lambda self: fake)
    client.force_login(user)
    resp = client.get(f"/checkout/pay/{order.order_number}/")
    assert resp.status_code == 302 and resp.url == f"/orders/{order.order_number}/"


@override_settings(ZARINPAL={"MERCHANT_ID": "m-123", "SANDBOX": True})
def test_zarinpal_error_message_is_shown(order, monkeypatch):
    fake = FakeRequests(FakeResponse({"data": [], "errors": {"code": -9, "message": "Amount is too low"}}))
    monkeypatch.setattr(ZarinPalGateway, "_client", lambda self: fake)
    assert ZarinPalGateway().create(order).result.message == "Amount is too low"


def test_callback_cannot_settle_mock_payments(client, order):
    start_payment(order=order)
    resp = client.get(f"/payments/callback/{order.order_number}/?outcome=success")
    assert resp.status_code == 404
    order.refresh_from_db()
    assert order.status == Order.Status.PENDING_PAYMENT
