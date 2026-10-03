import pytest

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product

ADDRESS = {
    "full_name": "a", "phone": "09120000000", "province": "p", "city": "c",
    "postal_code": "1234567890", "address_line": "x",
}


@pytest.mark.django_db
def test_order_email_links_point_at_the_live_site(django_user_model, mailoutbox, settings):
    from apps.orders.services import place_order

    settings.SITE_URL = "https://shop.example.ir"
    user = django_user_model.objects.create_user(email="b@example.com", password="x")
    product = Product.objects.create(category=Category.objects.create(name="c", slug="c"), name="p", slug="p",
                                     price=100, stock=3)
    cart = Cart.objects.create(user=user)
    CartItem.objects.create(cart=cart, product=product, quantity=1)
    order = place_order(user=user, cart=cart, address_data=ADDRESS)

    body = mailoutbox[-1].body
    assert f"https://shop.example.ir/orders/{order.order_number}/" in body
    assert "127.0.0.1" not in body


@pytest.mark.django_db
def test_robots_names_this_host_sitemap(client):
    body = client.get("/robots.txt", HTTP_HOST="testserver").content.decode()
    assert "Sitemap: http://testserver/sitemap.xml" in body
    assert "127.0.0.1" not in body
