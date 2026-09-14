"""Bug 2: cancelling from the admin must give back stock, coupon use and wallet money."""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.contrib import admin
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product
from apps.discounts.models import Coupon
from apps.orders.admin import OrderAdmin
from apps.orders.models import Order
from apps.orders.services import OrderError, needs_manual_refund, place_order, transition_status
from apps.payments.services import mark_paid
from apps.wallet import services as wallet_services
from apps.wallet.models import GiftCard, Wallet, WalletTransaction

ADDRESS = {
    "full_name": "a", "phone": "09120000000", "province": "پ",
    "city": "ش", "postal_code": "1234567890", "address_line": "addr",
}


@pytest.fixture
def user(db, django_user_model):
    return django_user_model.objects.create_user(email="cancel@example.com", password="x")


@pytest.fixture
def product(db):
    cat = Category.objects.create(name="c", slug="c")
    return Product.objects.create(category=cat, name="p", slug="p", price=100_000, stock=5)


@pytest.fixture
def coupon(db):
    return Coupon.objects.create(
        code="SAVE10", kind=Coupon.Kind.PERCENT, value=10,
        valid_from=timezone.now() - timedelta(days=1),
        valid_to=timezone.now() + timedelta(days=1),
    )


def make_order(user, product, **kwargs):
    cart = Cart.objects.create(user=user)
    CartItem.objects.create(cart=cart, product=product, quantity=2)
    return place_order(user=user, cart=cart, address_data=ADDRESS, **kwargs)


def test_cancelling_pending_order_releases_stock_and_coupon(user, product, coupon):
    order = make_order(user, product, coupon_code="SAVE10")
    product.refresh_from_db()
    coupon.refresh_from_db()
    assert (product.stock, coupon.used_count) == (3, 1)

    transition_status(order=order, new_status=Order.Status.CANCELLED)

    product.refresh_from_db()
    coupon.refresh_from_db()
    assert (product.stock, coupon.used_count) == (5, 0)


def test_cancelling_wallet_paid_order_refunds_the_wallet(user, product):
    GiftCard.objects.create(code="GIFT-REFUND", amount=500_000)
    wallet_services.redeem_gift_card(user=user, code="GIFT-REFUND")
    order = make_order(user, product, pay_with_wallet=True)
    assert Wallet.objects.get(user=user).balance == 500_000 - order.total

    order = transition_status(order=order, new_status=Order.Status.CANCELLED)

    assert Wallet.objects.get(user=user).balance == 500_000
    refund = WalletTransaction.objects.get(kind=WalletTransaction.Kind.ORDER_REFUND)
    assert (refund.amount, refund.order_id) == (order.total, order.pk)
    product.refresh_from_db()
    assert product.stock == 5
    assert needs_manual_refund(order) is False


def test_cancelling_gateway_paid_order_restores_stock_and_flags_manual_refund(user, product):
    order = make_order(user, product)
    mark_paid(order=order, ref="BANK-REF-1")

    order = transition_status(order=order, new_status=Order.Status.CANCELLED)

    product.refresh_from_db()
    assert product.stock == 5
    assert not WalletTransaction.objects.filter(kind=WalletTransaction.Kind.ORDER_REFUND).exists()
    assert needs_manual_refund(order) is True


def test_cancelled_order_cannot_be_cancelled_twice(user, product):
    order = make_order(user, product)
    transition_status(order=order, new_status=Order.Status.CANCELLED)
    with pytest.raises(OrderError):
        transition_status(order=order, new_status=Order.Status.CANCELLED)
    product.refresh_from_db()
    assert product.stock == 5  # released once, not twice


def test_admin_status_change_to_cancelled_goes_through_the_service(rf, admin_user, user, product, coupon):
    order = make_order(user, product, coupon_code="SAVE10")
    mark_paid(order=order, ref="BANK-REF-2")
    request = rf.post("/admin/orders/order/")
    request.user = admin_user
    request.session = {}
    request._messages = FallbackStorage(request)

    obj = Order.objects.get(pk=order.pk)
    obj.status = Order.Status.CANCELLED
    form = SimpleNamespace(
        changed_data=["status"],
        cleaned_data={"status": Order.Status.CANCELLED, "tracking_code": "", "shipping_note": ""},
    )
    OrderAdmin(Order, admin.site).save_model(request, obj, form, change=True)

    order.refresh_from_db()
    product.refresh_from_db()
    coupon.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
    assert (product.stock, coupon.used_count) == (5, 0)
    texts = [str(m) for m in get_messages(request)]
    assert any("لغو شد" in t for t in texts)
    assert any("دستی" in t for t in texts)  # finance is told to refund the bank payment
