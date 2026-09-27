import pytest
from django.urls import reverse

from apps.catalog.models import Category, Product
from apps.common.models import SiteSettings
from apps.orders.models import Order, ShippingMethod
from apps.orders.services import OrderError, place_order
from apps.cart.models import Cart, CartItem
from apps.wallet import services as wallet_services


ADDRESS = {
    "full_name": "a", "phone": "09120000000", "province": "پ",
    "city": "ش", "postal_code": "1234567890", "address_line": "addr",
}


@pytest.fixture
def user(db, django_user_model):
    return django_user_model.objects.create_user(email="buyer2@example.com", password="x")


@pytest.fixture
def product(db):
    cat = Category.objects.create(name="c", slug="c")
    return Product.objects.create(category=cat, name="p", slug="p", price=100_000, stock=5)


@pytest.fixture
def cart_with_item(user, product):
    cart = Cart.objects.create(user=user)
    CartItem.objects.create(cart=cart, product=product, quantity=2)
    return cart


def test_shipping_method_price_applied(user, cart_with_item):
    m = ShippingMethod.objects.create(name="پیک", price=30_000, is_active=True)
    order = place_order(user=user, cart=cart_with_item, address_data=ADDRESS, shipping_method=m)
    assert order.shipping_method_id == m.pk
    assert order.shipping_cost == 30_000
    assert order.total == 200_000 + 30_000


def test_free_shipping_overrides_method_price(user, cart_with_item):
    s = SiteSettings.load()
    s.free_shipping_threshold = 200_000
    s.save()
    m = ShippingMethod.objects.create(name="باربری", price=100_000, is_active=True)
    order = place_order(user=user, cart=cart_with_item, address_data=ADDRESS, shipping_method=m)
    assert order.shipping_cost == 0


def test_install_fee_applied_when_requested(user, cart_with_item):
    s = SiteSettings.load()
    s.install_fee = 40_000
    s.save()
    order = place_order(user=user, cart=cart_with_item, address_data=ADDRESS, install_requested=True)
    assert order.install_requested is True
    assert order.install_cost == 40_000
    assert order.total == 200_000 + 50_000 + 40_000  # shipping default 50k


def test_install_not_charged_when_not_requested(user, cart_with_item):
    s = SiteSettings.load()
    s.install_fee = 40_000
    s.save()
    order = place_order(user=user, cart=cart_with_item, address_data=ADDRESS, install_requested=False)
    assert order.install_cost == 0
    assert order.total == 250_000  # 200k items + 50k shipping, no install


def test_wallet_pays_full_order(user, cart_with_item):
    wallet_services.get_wallet(user)
    from apps.wallet.models import GiftCard
    GiftCard.objects.create(code="GIFT-CHECKOUT", amount=250_000)
    wallet_services.redeem_gift_card(user=user, code="GIFT-CHECKOUT")
    order = place_order(user=user, cart=cart_with_item, address_data=ADDRESS, pay_with_wallet=True)
    order.refresh_from_db()
    assert order.status == Order.Status.PAID
    assert order.wallet_used == order.total
    assert order.payment_ref == "WALLET"
    from apps.wallet.models import Wallet
    assert Wallet.objects.get(user=user).balance == 250_000 - order.total


def test_wallet_insufficient_aborts_and_rolls_back(user, cart_with_item, product):
    wallet_services.get_wallet(user)  # balance 0
    before_stock = product.stock
    with pytest.raises(OrderError):
        place_order(user=user, cart=cart_with_item, address_data=ADDRESS, pay_with_wallet=True)
    # rollback: order not created, stock intact, cart intact
    assert Order.objects.count() == 0
    product.refresh_from_db()
    assert product.stock == before_stock
    cart_with_item.refresh_from_db()
    assert cart_with_item.items.count() == 1


def test_full_value_coupon_with_free_shipping_needs_no_payment(user, cart_with_item):
    from datetime import timedelta

    from django.utils import timezone

    from apps.discounts.models import Coupon

    s = SiteSettings.load()
    s.free_shipping_threshold = 1
    s.save()
    Coupon.objects.create(
        code="GIFT100", kind="percent", value=100,
        valid_from=timezone.now() - timedelta(days=1), valid_to=timezone.now() + timedelta(days=1),
    )
    order = place_order(user=user, cart=cart_with_item, address_data=ADDRESS, coupon_code="GIFT100")
    assert order.total == 0
    assert order.status == Order.Status.PAID


def _checkout_post(client, user, **overrides):
    client.force_login(user)
    return client.post(reverse("orders:place"), {**ADDRESS, **overrides})


def test_overlong_typed_address_is_rejected_not_crashing(client, user, cart_with_item):
    response = _checkout_post(client, user, postal_code="1" * 40)
    assert response.status_code == 302 and response.url.endswith("/checkout/")
    assert not Order.objects.exists()


def test_malformed_ids_in_checkout_form_do_not_crash(client, user, cart_with_item):
    assert _checkout_post(client, user, address_id="abc").status_code == 404
    response = _checkout_post(client, user, shipping_method="abc")
    assert response.status_code == 302
    assert Order.objects.count() == 1


def test_typed_address_is_saved_only_when_order_goes_through(client, user, cart_with_item, product):
    from apps.accounts.models import Address

    Product.objects.filter(pk=product.pk).update(stock=0)
    _checkout_post(client, user, save_address="on")
    assert not Address.objects.exists()
