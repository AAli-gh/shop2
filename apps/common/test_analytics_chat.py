import json
import re

import pytest
from django.core.exceptions import ValidationError

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product
from apps.common.models import SiteSettings
from apps.orders.services import place_order

ADDRESS = {
    "full_name": "مریم احمدی", "phone": "09121234567", "province": "تهران",
    "city": "تهران", "postal_code": "1234567890", "address_line": "خیابان آزادی",
}


@pytest.fixture
def product(db):
    category = Category.objects.create(name="یخچال", slug="fridge")
    return Product.objects.create(category=category, name="یخچال ساید", slug="side", price=50_000_000, stock=5)


@pytest.fixture
def tracking(db):
    site = SiteSettings.load()
    site.ga_measurement_id = "G-TEST1234"
    site.save()
    return site


def _events(html, name):
    """Parameters of every shopTrack(name, {...}) call in the page."""
    return [json.loads(m) for m in re.findall(rf'shopTrack\("{name}",(\{{.*?\}})\);', html)]


@pytest.mark.django_db
def test_no_google_code_without_a_measurement_id(client, product):
    body = client.get(product.get_absolute_url()).content.decode()
    assert "googletagmanager" not in body
    assert "window.shopTrack" in body  # the no-op hook still exists for templates
    assert '"view_item"' not in body


def test_product_page_loads_ga_and_reports_the_view(client, product, tracking):
    body = client.get(product.get_absolute_url()).content.decode()

    assert "googletagmanager.com/gtag/js?id=G-TEST1234" in body
    (event,) = _events(body, "view_item")
    assert event["currency"] == "IRR" and event["value"] == 500_000_000
    assert event["items"][0]["item_name"] == "یخچال ساید"


def test_cart_checkout_and_purchase_events(client, product, tracking, django_user_model):
    customer = django_user_model.objects.create_user(email="buyer@example.com", password="x")
    client.force_login(customer)

    added = client.post(f"/cart/htmx/add/{product.pk}/", {"quantity": 2}).content.decode()
    (event,) = _events(added, "add_to_cart")
    assert event["value"] == 1_000_000_000 and event["items"][0]["quantity"] == 2

    checkout = client.get("/checkout/").content.decode()
    assert _events(checkout, "begin_checkout")[0]["value"] == 1_000_000_000

    order = place_order(user=customer, cart=Cart.objects.get(user=customer), address_data=ADDRESS)
    success = client.get(f"/orders/{order.order_number}/success/").content.decode()
    assert f'"transaction_id": "{order.order_number}"' in success
    assert f"ga-purchase-{order.order_number}" in success  # counted once per browser session


def test_chat_buttons_and_widget(client, db):
    site = SiteSettings.load()
    site.whatsapp_number = "989121234567"
    site.telegram_username = "shop_support"
    site.chat_widget_html = "<script>/* live chat */</script>"
    site.save()

    body = client.get("/").content.decode()

    assert 'href="https://wa.me/989121234567?text=' in body
    assert 'href="https://t.me/shop_support"' in body
    assert "/* live chat */" in body


@pytest.mark.django_db
@pytest.mark.parametrize("field, value", [
    ("ga_measurement_id", "UA-12345-1"),
    ("ga_measurement_id", 'G-1"><script>'),
    ("whatsapp_number", "09121234567"),
    ("telegram_username", "@shop"),
])
def test_contact_and_analytics_settings_are_validated(field, value):
    site = SiteSettings.load()
    setattr(site, field, value)
    with pytest.raises(ValidationError) as exc:
        site.full_clean()
    assert field in exc.value.message_dict
