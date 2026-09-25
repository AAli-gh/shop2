import pytest
from django.conf import settings as django_settings

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product
from apps.common import sms
from apps.common.sms import LocmemSmsBackend
from apps.common.test_prod_settings import run_python
from apps.common.test_sms import fake_client
from apps.orders.models import Order
from apps.orders.services import place_order, transition_status
from apps.payments.services import mark_paid

SMSIR = {
    "API_KEY": "key-123", "LINE_NUMBER": "30007732000000", "OTP_TEMPLATE_ID": 456789, "OTP_PARAMETER": "CODE",
    "TEMPLATES": {"order_status": 111, "price_drop": 0},
}
ADDRESS = {
    "full_name": "مریم احمدی", "phone": "09121234567", "province": "تهران",
    "city": "تهران", "postal_code": "1234567890", "address_line": "خیابان آزادی",
}


@pytest.fixture
def smsir(settings):
    settings.SMS_BACKEND = "apps.common.sms.SmsIrBackend"
    settings.SMSIR = SMSIR


def test_an_event_with_a_template_goes_through_verify(smsir, monkeypatch):
    fake = fake_client(monkeypatch, {"status": 1, "message": "موفق"})

    sent = sms.notify("09121234567", "متن کامل", event="order_status", params={"ORDER": "SH-1", "STATUS": "ارسال شد"})

    assert sent is True
    call = fake.calls[0]
    assert call["url"] == "https://api.sms.ir/v1/send/verify"
    assert call["json"] == {
        "mobile": "09121234567", "templateId": 111,
        "parameters": [{"name": "ORDER", "value": "SH-1"}, {"name": "STATUS", "value": "ارسال شد"}],
    }


def test_long_parameter_values_are_cut(smsir, monkeypatch):
    fake = fake_client(monkeypatch, {"status": 1, "message": "موفق"})
    sms.notify("09121234567", "x", event="order_status", params={"ORDER": "SH-1", "STATUS": "و" * 40})
    assert len(fake.calls[0]["json"]["parameters"][1]["value"]) == sms.PARAM_MAX_LENGTH


def test_an_event_without_a_template_is_texted_from_the_line(smsir, monkeypatch):
    fake = fake_client(monkeypatch, {"status": 1, "message": "موفق"})
    sms.notify("09121234567", "قیمت کم شد", event="price_drop", params={"PRODUCT": "یخچال", "PRICE": "1,000"})
    assert fake.calls[0]["url"] == "https://api.sms.ir/v1/send/bulk"
    assert fake.calls[0]["json"]["messageText"] == "قیمت کم شد"


def test_settings_and_parameters_cover_the_same_events():
    assert set(django_settings.SMSIR["TEMPLATES"]) == set(sms.EVENT_PARAMETERS)


def test_template_ids_come_from_environment_variables():
    code = "import django; django.setup(); from django.conf import settings as s; print(s.SMSIR['TEMPLATES']['order_status'])"
    result = run_python(["-c", code], SMSIR_TEMPLATE_ORDER_STATUS="123456")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "123456"


@pytest.mark.django_db
def test_order_notifications_name_their_event(django_user_model, settings, django_capture_on_commit_callbacks):
    settings.ORDER_NOTIFY_PHONES = ["09350000000"]
    customer = django_user_model.objects.create_user(phone="09121234567", phone_verified=True)
    category = Category.objects.create(name="c", slug="c")
    product = Product.objects.create(category=category, name="همزن", slug="mixer", price=2_000_000, stock=5)
    cart = Cart.objects.create(user=customer)
    CartItem.objects.create(cart=cart, product=product, quantity=1)

    with django_capture_on_commit_callbacks(execute=True):
        order = place_order(user=customer, cart=cart, address_data=ADDRESS)
        mark_paid(order=order, ref="REF-1")
        transition_status(order=Order.objects.get(pk=order.pk), new_status=Order.Status.PROCESSING)

    events = {(m["phone"], m.get("event")): m.get("params") for m in LocmemSmsBackend.outbox}
    assert events[("09121234567", "order_placed")] == {"ORDER": order.order_number, "AMOUNT": f"{order.total:,}"}
    assert events[("09121234567", "order_status")]["ORDER"] == order.order_number
    assert events[("09350000000", "order_paid_staff")]["ORDER"] == order.order_number
