import json

import pytest
from django.test import override_settings

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product
from apps.common import sms
from apps.common.sms import FileSmsBackend, LocmemSmsBackend, SmsError, SmsIrBackend

SMSIR = {"API_KEY": "key-123", "LINE_NUMBER": "30007732000000", "OTP_TEMPLATE_ID": 456789, "OTP_PARAMETER": "CODE"}


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeRequests:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, json=None, timeout=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return self.response


def fake_client(monkeypatch, payload, status_code=200):
    fake = FakeRequests(FakeResponse(payload, status_code))
    monkeypatch.setattr(SmsIrBackend, "_client", lambda self: fake)
    return fake


@override_settings(SMSIR=SMSIR)
def test_smsir_sends_code_through_verify_template(monkeypatch):
    fake = fake_client(monkeypatch, {"status": 1, "message": "موفق", "data": {"messageId": 1}})
    SmsIrBackend().send_otp("09121234567", "12345")
    call = fake.calls[0]
    assert call["url"] == "https://api.sms.ir/v1/send/verify"
    assert call["headers"]["X-API-KEY"] == "key-123"
    assert call["json"] == {
        "mobile": "09121234567", "templateId": 456789,
        "parameters": [{"name": "CODE", "value": "12345"}],
    }


@override_settings(SMSIR=SMSIR)
def test_smsir_sends_text_from_line_number(monkeypatch):
    fake = fake_client(monkeypatch, {"status": 1, "message": "موفق"})
    SmsIrBackend().send_text("09121234567", "سلام")
    assert fake.calls[0]["url"] == "https://api.sms.ir/v1/send/bulk"
    assert fake.calls[0]["json"] == {"lineNumber": 30007732000000, "messageText": "سلام", "mobiles": ["09121234567"]}


@override_settings(SMSIR=SMSIR)
def test_smsir_rejection_raises(monkeypatch):
    fake_client(monkeypatch, {"status": 0, "message": "قالب نامعتبر"}, status_code=400)
    with pytest.raises(SmsError):
        SmsIrBackend().send_otp("09121234567", "12345")


@override_settings(SMSIR={**SMSIR, "API_KEY": ""})
def test_smsir_without_api_key_raises():
    with pytest.raises(SmsError):
        SmsIrBackend().send_otp("09121234567", "12345")


def test_notify_never_raises(monkeypatch, caplog):
    def broken(self, phone, text):
        raise SmsError("down")

    monkeypatch.setattr(LocmemSmsBackend, "send_text", broken)
    assert sms.notify("09121234567", "x") is False
    assert sms.notify("", "x") is False


def test_file_backend_writes_messages(settings, tmp_path):
    settings.SMS_FILE_PATH = tmp_path
    FileSmsBackend().send_otp("09121234567", "54321")
    content = next(tmp_path.iterdir()).read_text(encoding="utf-8")
    assert "09121234567" in content and "54321" in content


@pytest.mark.django_db
def test_phone_customers_get_order_texts_instead_of_email(django_user_model, mailoutbox):
    from apps.orders.services import place_order

    user = django_user_model.objects.create_user(phone="09121234567", phone_verified=True)
    cat = Category.objects.create(name="c", slug="c")
    product = Product.objects.create(category=cat, name="p", slug="p", price=100_000, stock=5)
    cart = Cart.objects.create(user=user)
    CartItem.objects.create(cart=cart, product=product, quantity=1)
    address = {"full_name": "a", "phone": "09121234567", "province": "پ", "city": "ش",
               "postal_code": "1234567890", "address_line": "addr"}

    order = place_order(user=user, cart=cart, address_data=address)

    assert mailoutbox == []  # no email address, nothing to send
    texts = [m["text"] for m in LocmemSmsBackend.outbox if m["phone"] == "09121234567"]
    assert any(order.order_number in t for t in texts)
