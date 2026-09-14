from datetime import timedelta
from io import BytesIO
from types import SimpleNamespace

import pytest
from django.contrib import admin
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product
from apps.common.models import SiteSettings
from apps.common.sms import LocmemSmsBackend
from apps.orders import returns
from apps.orders.admin import ReturnRequestAdmin
from apps.orders.models import Order, ReturnRequest
from apps.orders.services import place_order, transition_status
from apps.payments.services import mark_paid

ADDRESS = {
    "full_name": "مریم احمدی", "phone": "09121234567", "province": "تهران",
    "city": "تهران", "postal_code": "1234567890", "address_line": "خیابان آزادی",
}


@pytest.fixture
def customer(db, django_user_model):
    return django_user_model.objects.create_user(email="buyer@example.com", password="x", phone="09121234567",
                                                 phone_verified=True)


@pytest.fixture
def products(db):
    cat = Category.objects.create(name="c", slug="c")
    return [
        Product.objects.create(category=cat, name="یخچال", slug="fridge", price=1_000_000, stock=10),
        Product.objects.create(category=cat, name="همزن", slug="mixer", price=250_000, stock=10),
    ]


def make_order(user, products, quantities=(1, 2)):
    cart, _ = Cart.objects.get_or_create(user=user)
    for product, qty in zip(products, quantities):
        CartItem.objects.create(cart=cart, product=product, quantity=qty)
    return place_order(user=user, cart=cart, address_data=ADDRESS)


def deliver(order, days_ago=1):
    mark_paid(order=order, ref="REF-1")
    for status in (Order.Status.PROCESSING, Order.Status.SHIPPED, Order.Status.DELIVERED):
        transition_status(order=order, new_status=status)
    Order.objects.filter(pk=order.pk).update(delivered_at=timezone.now() - timedelta(days=days_ago))
    order.refresh_from_db()
    return order


def png(size=(10, 10)):
    buffer = BytesIO()
    Image.new("RGB", size, "white").save(buffer, "PNG")
    return SimpleUploadedFile("photo.png", buffer.getvalue(), content_type="image/png")


# ---------------------------------------------------------------- invoice

def test_owner_gets_printable_invoice_with_amount_in_words(client, customer, products):
    settings_obj = SiteSettings.load()
    settings_obj.legal_name = "فروشگاه اعتماد"
    settings_obj.economic_code = "411111111111"
    settings_obj.save()
    order = make_order(customer, products)  # 1×1,000,000 + 2×250,000 + 50,000 shipping
    client.force_login(customer)

    body = client.get(f"/orders/{order.order_number}/invoice/").content.decode()

    assert "پیش‌فاکتور" in body  # not paid yet
    assert order.order_number in body and "یخچال" in body and "همزن" in body
    assert "۱,۵۵۰,۰۰۰" in body
    assert "یک میلیون و پانصد و پنجاه هزار تومان" in body
    assert "فروشگاه اعتماد" in body and "۴۱۱۱۱۱۱۱۱۱۱۱" in body
    assert "مریم احمدی" in body
    assert "window.print()" in body


def test_paid_order_is_a_sales_invoice(client, customer, products):
    order = make_order(customer, products)
    mark_paid(order=order, ref="REF-9")
    client.force_login(customer)
    body = client.get(f"/orders/{order.order_number}/invoice/").content.decode()
    assert "فاکتور فروش" in body and "پیش‌فاکتور" not in body.split("<body")[1]


def test_invoice_is_private_but_staff_can_open_any(client, customer, products, django_user_model, admin_user):
    order = make_order(customer, products)
    url = f"/orders/{order.order_number}/invoice/"

    assert client.get(url).url.startswith("/accounts/login/")
    client.force_login(django_user_model.objects.create_user(email="other@example.com", password="x"))
    assert client.get(url).status_code == 404
    client.force_login(admin_user)
    assert client.get(url).status_code == 200


def test_order_page_links_to_invoice(client, customer, products):
    order = make_order(customer, products)
    client.force_login(customer)
    assert f"/orders/{order.order_number}/invoice/" in client.get(f"/orders/{order.order_number}/").content.decode()


# ---------------------------------------------------------------- return eligibility

def test_delivery_records_the_date(customer, products):
    order = make_order(customer, products)
    mark_paid(order=order, ref="R")
    for status in (Order.Status.PROCESSING, Order.Status.SHIPPED, Order.Status.DELIVERED):
        order = transition_status(order=order, new_status=status)
    assert order.delivered_at is not None


def test_returns_only_after_delivery_and_within_the_window(customer, products, settings):
    settings.RETURN_WINDOW_DAYS = 7
    order = make_order(customer, products)
    assert "پس از تحویل" in returns.return_block_reason(order)

    deliver(order, days_ago=2)
    assert returns.return_block_reason(order) == ""

    Order.objects.filter(pk=order.pk).update(delivered_at=timezone.now() - timedelta(days=8))
    order.refresh_from_db()
    assert "مهلت" in returns.return_block_reason(order)


def test_one_open_request_per_order_but_rejected_ones_free_it(customer, products):
    order = deliver(make_order(customer, products))
    fridge = order.items.get(product_name="یخچال")
    request = returns.create_return_request(order=order, quantities={fridge.pk: 1}, reason="defective",
                                            resolution="refund", description="روشن نمی‌شود اصلاً")
    assert "در حال بررسی" in returns.return_block_reason(order)

    returns.set_return_status(return_request=request, status=ReturnRequest.Status.REJECTED)
    assert returns.return_block_reason(order) == ""
    assert returns.returnable_quantities(order)[fridge.pk] == 1  # rejected units are returnable again


# ---------------------------------------------------------------- creating a request

def test_quantities_are_validated(customer, products):
    order = deliver(make_order(customer, products))
    mixer = order.items.get(product_name="همزن")
    common = {"reason": "damaged", "resolution": "replace", "description": "بدنه شکسته است"}

    with pytest.raises(returns.ReturnError):
        returns.create_return_request(order=order, quantities={mixer.pk: 0}, **common)
    with pytest.raises(returns.ReturnError):
        returns.create_return_request(order=order, quantities={mixer.pk: 3}, **common)  # only 2 bought
    other = deliver(make_order(customer, products))
    with pytest.raises(returns.ReturnError):
        returns.create_return_request(order=order, quantities={other.items.first().pk: 1}, **common)

    request = returns.create_return_request(order=order, quantities={mixer.pk: 2}, **common)
    assert [(i.order_item_id, i.quantity) for i in request.items.all()] == [(mixer.pk, 2)]


def test_return_form_submission(client, customer, products, mailoutbox, settings):
    settings.ADMINS = [("Shop", "team@example.com")]
    order = deliver(make_order(customer, products))
    mixer = order.items.get(product_name="همزن")
    client.force_login(customer)
    url = f"/orders/{order.order_number}/return/"

    assert client.get(url).status_code == 200
    resp = client.post(url, {
        f"qty_{mixer.pk}": "1", "reason": "not_as_described", "resolution": "refund",
        "description": "رنگ کالا با عکس سایت فرق دارد", "image": png(),
    })

    assert resp.url == f"/orders/{order.order_number}/"
    request = ReturnRequest.objects.get(order=order)
    assert request.image and request.items.get().quantity == 1
    assert any("team@example.com" in m.to and order.order_number in m.subject for m in mailoutbox)
    assert "در انتظار بررسی" in client.get(resp.url).content.decode()


def test_return_form_rejects_nothing_selected_and_big_photos(client, customer, products):
    order = deliver(make_order(customer, products))
    client.force_login(customer)
    url = f"/orders/{order.order_number}/return/"
    base = {"reason": "other", "resolution": "refund", "description": "توضیحات کافی برای درخواست"}

    resp = client.post(url, base)
    assert resp.status_code == 200 and "حداقل یک کالا" in resp.content.decode()

    big = SimpleUploadedFile("big.png", b"0" * (3 * 1024 * 1024 + 1), content_type="image/png")
    resp = client.post(url, {**base, f"qty_{order.items.first().pk}": "1", "image": big})
    assert resp.status_code == 200
    assert not ReturnRequest.objects.exists()


def test_return_form_for_undelivered_or_foreign_orders(client, customer, products, django_user_model):
    order = make_order(customer, products)
    client.force_login(customer)
    assert client.get(f"/orders/{order.order_number}/return/").url == f"/orders/{order.order_number}/"

    client.force_login(django_user_model.objects.create_user(email="x@example.com", password="x"))
    assert client.get(f"/orders/{order.order_number}/return/").status_code == 404


# ---------------------------------------------------------------- staff workflow

def test_status_workflow_notifies_the_customer(customer, products, mailoutbox):
    order = deliver(make_order(customer, products))
    request = returns.create_return_request(order=order, quantities={order.items.first().pk: 1},
                                            reason="defective", resolution="refund", description="صدای عجیب می‌دهد")
    LocmemSmsBackend.outbox.clear()

    returns.set_return_status(return_request=request, status=ReturnRequest.Status.APPROVED,
                              staff_note="کالا را با پیک ارسال کنید.")

    assert any(order.order_number in m["text"] and "تأیید شد" in m["text"] for m in LocmemSmsBackend.outbox)
    assert any("کالا را با پیک ارسال کنید." in m.body for m in mailoutbox)
    with pytest.raises(returns.ReturnError):  # can't skip "received"
        returns.set_return_status(return_request=request, status=ReturnRequest.Status.COMPLETED)


def test_admin_status_change_uses_the_workflow(rf, admin_user, customer, products):
    order = deliver(make_order(customer, products))
    request = returns.create_return_request(order=order, quantities={order.items.first().pk: 1},
                                            reason="wrong_item", resolution="replace", description="مدل دیگری آمده")
    http = rf.post("/admin/")
    http.user, http.session = admin_user, {}
    http._messages = FallbackStorage(http)
    obj = ReturnRequest.objects.get(pk=request.pk)
    obj.status = ReturnRequest.Status.COMPLETED  # not allowed straight from pending
    form = SimpleNamespace(changed_data=["status"], cleaned_data={"status": obj.status, "staff_note": ""})

    ReturnRequestAdmin(ReturnRequest, admin.site).save_model(http, obj, form, change=True)

    request.refresh_from_db()
    assert request.status == ReturnRequest.Status.PENDING
