from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from django.contrib import admin
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product
from apps.common.admin_jalali import jalali_range, to_jalali
from apps.common.sms import LocmemSmsBackend
from apps.discounts.models import Coupon
from apps.orders import returns
from apps.orders.admin import OrderAdmin
from apps.orders.models import Order, OrderNote, ReturnRequest
from apps.orders.services import place_order, transition_status
from apps.payments.services import mark_paid
from apps.wallet import services as wallet_services
from apps.wallet.models import GiftCard, Wallet, WalletTransaction

ADDRESS = {
    "full_name": "مریم احمدی", "phone": "09351112233", "province": "تهران",
    "city": "تهران", "postal_code": "1234567890", "address_line": "خیابان آزادی",
}


@pytest.fixture
def customer(db, django_user_model):
    return django_user_model.objects.create_user(phone="09121234567", phone_verified=True, name="علی رضایی")


@pytest.fixture
def products(db):
    cat = Category.objects.create(name="c", slug="c")
    return {
        "fridge": Product.objects.create(category=cat, name="یخچال", slug="fridge", price=1_000_000, stock=10),
        "mixer": Product.objects.create(category=cat, name="همزن", slug="mixer", price=250_000, stock=10),
    }


def make_order(user, products, address=ADDRESS, **kwargs):
    cart, _ = Cart.objects.get_or_create(user=user)
    CartItem.objects.create(cart=cart, product=products["fridge"], quantity=1)
    CartItem.objects.create(cart=cart, product=products["mixer"], quantity=2)
    return place_order(user=user, cart=cart, address_data=address, **kwargs)


# ---------------------------------------------------------------- search

@pytest.mark.parametrize("query", ["۰۹۱۲۱۲۳۴۵۶۷", "+989121234567", "علی رضایی", "مریم احمدی", "09351112233"])
def test_orders_are_searchable_by_mobile_and_name(admin_client, customer, products, django_user_model, query):
    order = make_order(customer, products)
    other_user = django_user_model.objects.create_user(email="other@example.com", password="x")
    other = make_order(other_user, products, address={**ADDRESS, "full_name": "سارا کریمی", "phone": "09190000000"})

    body = admin_client.get("/admin/orders/order/", {"q": query}).content.decode()

    assert order.order_number in body
    assert other.order_number not in body


# ---------------------------------------------------------------- internal notes

class NoteFormset:
    """Just enough of an inline formset for OrderAdmin.save_formset."""

    model = OrderNote
    deleted_objects = []

    def __init__(self, instances):
        self.instances = instances

    def save(self, commit=True):
        return self.instances

    def save_m2m(self):
        pass


def test_internal_note_records_author_and_stays_private(rf, admin_user, admin_client, client, customer, products):
    order = make_order(customer, products)
    request = rf.post("/admin/")
    request.user = admin_user
    note = OrderNote(order=order, body="مشتری خواست قبل از ارسال تماس بگیریم")

    OrderAdmin(Order, admin.site).save_formset(request, None, NoteFormset([note]), change=True)

    note.refresh_from_db()
    assert note.author == admin_user
    assert note.body in admin_client.get(f"/admin/orders/order/{order.pk}/change/").content.decode()
    client.force_login(customer)
    assert note.body not in client.get(f"/orders/{order.order_number}/").content.decode()


# ---------------------------------------------------------------- manager alert

@pytest.fixture
def managers(settings):
    settings.ORDER_NOTIFY_PHONES = ["09350000000"]
    settings.ORDER_NOTIFY_EMAILS = ["ops@example.com"]


def manager_texts():
    return [m["text"] for m in LocmemSmsBackend.outbox if m["phone"] == "09350000000"]


def test_managers_are_alerted_when_an_order_is_paid(managers, customer, products, mailoutbox,
                                                    django_capture_on_commit_callbacks):
    order = make_order(customer, products)
    assert manager_texts() == []  # an unpaid order is not news yet

    with django_capture_on_commit_callbacks(execute=True):
        mark_paid(order=order, ref="REF-1")

    assert any(order.order_number in text for text in manager_texts())
    assert any("ops@example.com" in m.to and order.order_number in m.subject for m in mailoutbox)


def test_wallet_paid_and_admin_marked_orders_alert_too(managers, customer, products,
                                                       django_capture_on_commit_callbacks):
    GiftCard.objects.create(code="GIFT-ALERT", amount=5_000_000)
    wallet_services.redeem_gift_card(user=customer, code="GIFT-ALERT")
    with django_capture_on_commit_callbacks(execute=True):
        wallet_order = make_order(customer, products, pay_with_wallet=True)
    manual_order = make_order(customer, products)
    with django_capture_on_commit_callbacks(execute=True):
        transition_status(order=manual_order, new_status=Order.Status.PAID)

    texts = " ".join(manager_texts())
    assert wallet_order.order_number in texts and manual_order.order_number in texts


# ---------------------------------------------------------------- completing a return

@pytest.fixture
def received_return(customer, products):
    Coupon.objects.create(code="TEN", kind=Coupon.Kind.PERCENT, value=10,
                          valid_from=timezone.now() - timedelta(days=1), valid_to=timezone.now() + timedelta(days=1))
    order = make_order(customer, products, coupon_code="TEN")  # subtotal 1,500,000, discount 150,000
    mark_paid(order=order, ref="REF")
    for status in (Order.Status.PROCESSING, Order.Status.SHIPPED, Order.Status.DELIVERED):
        transition_status(order=order, new_status=status)
    order.refresh_from_db()
    mixer_line = order.items.get(product_name="همزن")
    request = returns.create_return_request(order=order, quantities={mixer_line.pk: 1}, reason="defective",
                                            resolution="refund", description="موتور همزن کار نمی‌کند")
    returns.set_return_status(return_request=request, status=ReturnRequest.Status.APPROVED)
    returns.set_return_status(return_request=request, status=ReturnRequest.Status.RECEIVED)
    return request


def test_refund_excludes_the_items_share_of_the_discount(received_return):
    # 250,000 - 150,000 × 250,000 / 1,500,000
    assert returns.suggested_refund(received_return) == 225_000


def test_completing_refunds_wallet_and_restocks(received_return, customer, products):
    mixer = products["mixer"]
    mixer.refresh_from_db()
    stock_before, sold_before = mixer.stock, mixer.sold_count
    LocmemSmsBackend.outbox.clear()

    completed = returns.complete_return(return_request=received_return, refund_to_wallet=True, restock=True)

    assert (completed.status, completed.refund_amount, completed.restocked) == (ReturnRequest.Status.COMPLETED, 225_000, True)
    assert Wallet.objects.get(user=customer).balance == 225_000
    assert WalletTransaction.objects.filter(kind=WalletTransaction.Kind.ORDER_REFUND, amount=225_000).exists()
    mixer.refresh_from_db()
    assert (mixer.stock, mixer.sold_count) == (stock_before + 1, sold_before - 1)
    assert any("225,000" in m["text"] for m in LocmemSmsBackend.outbox if m["phone"] == customer.phone)

    with pytest.raises(returns.ReturnError):  # can't be completed (and refunded) twice
        returns.complete_return(return_request=received_return, refund_to_wallet=True, restock=True)


def test_completing_without_refund_or_restock(received_return, customer, products):
    mixer = products["mixer"]
    mixer.refresh_from_db()
    stock_before = mixer.stock
    returns.complete_return(return_request=received_return, refund_to_wallet=False, restock=False)
    assert not Wallet.objects.filter(user=customer, balance__gt=0).exists()
    mixer.refresh_from_db()
    assert mixer.stock == stock_before


def test_completion_only_through_the_dedicated_step(received_return):
    with pytest.raises(returns.ReturnError):
        returns.set_return_status(return_request=received_return, status=ReturnRequest.Status.COMPLETED)


def test_admin_complete_page(admin_client, received_return, customer):
    url = f"/admin/orders/returnrequest/{received_return.pk}/complete/"
    page = admin_client.get(url).content.decode()
    assert "225,000" in page

    resp = admin_client.post(url, {"refund_to_wallet": "on", "restock": "on", "staff_note": "وجه برگشت داده شد"})

    assert resp.status_code == 302
    received_return.refresh_from_db()
    assert received_return.status == ReturnRequest.Status.COMPLETED
    assert received_return.staff_note == "وجه برگشت داده شد"
    assert Wallet.objects.get(user=customer).balance == 225_000


# ---------------------------------------------------------------- jalali admin

def test_to_jalali():
    nowruz_noon_tehran = datetime(2026, 3, 21, 8, 30, tzinfo=dt_timezone.utc)
    assert to_jalali(nowruz_noon_tehran) == "1405/01/01 12:00"
    assert to_jalali(None) == "—"


def test_jalali_ranges_follow_the_shamsi_calendar():
    now = datetime(2026, 9, 14, 8, 30, tzinfo=dt_timezone.utc)  # 23 Shahrivar 1405, Tehran
    local = lambda d: timezone.localtime(d).date().isoformat()  # noqa: E731

    start, end = jalali_range("this_month", now)
    assert (local(start), local(end)) == ("2026-08-23", "2026-09-15")
    start, end = jalali_range("last_month", now)
    assert (local(start), local(end)) == ("2026-07-23", "2026-08-23")
    start, _ = jalali_range("this_year", now)
    assert local(start) == "2026-03-21"


def test_order_changelist_shows_jalali_and_filters_by_it(admin_client, customer, products):
    order = make_order(customer, products)
    today = to_jalali(order.created_at, "%Y/%m/%d")

    assert today in admin_client.get("/admin/orders/order/").content.decode()
    assert order.order_number in admin_client.get("/admin/orders/order/", {"created_at_jalali": "today"}).content.decode()
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(days=40))
    assert order.order_number not in admin_client.get("/admin/orders/order/", {"created_at_jalali": "7d"}).content.decode()
