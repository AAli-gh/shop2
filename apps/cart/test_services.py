import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.db import SessionStore

from apps.cart import services
from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product


@pytest.fixture
def product(db):
    cat = Category.objects.create(name="c", slug="c")
    return Product.objects.create(category=cat, name="p", slug="p", price=10_000, stock=3)


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(email="u@example.com", password="x")


class FakeRequest:
    def __init__(self):
        self.session = SessionStore()
        self.session.create()
        self.user = AnonymousUser()


def test_guest_cart_created_and_persisted(product):
    request = FakeRequest()
    cart = services.get_or_create_cart(request)
    services.add_to_cart(request, product_id=product.pk, quantity=2)
    assert request.session["cart_id"] == cart.pk
    assert cart.items.first().quantity == 2


def test_add_to_cart_caps_at_stock(product):
    request = FakeRequest()
    services.add_to_cart(request, product_id=product.pk, quantity=10)
    assert CartItem.objects.first().quantity == 3


def test_add_to_cart_rejects_zero_stock(db):
    cat = Category.objects.get(pk=1) if Category.objects.exists() else Category.objects.create(name="c2", slug="c2")
    p = Product.objects.create(category=cat, name="x", slug="x", price=1, stock=0)
    request = FakeRequest()
    with pytest.raises(services.CartError):
        services.add_to_cart(request, product_id=p.pk)


def test_merge_guest_cart_into_existing_user_cart(user, product):
    request = FakeRequest()
    guest_cart = services.get_or_create_cart(request)
    services.add_to_cart(request, product_id=product.pk, quantity=2)

    user_cart = Cart.objects.create(user=user)
    CartItem.objects.create(cart=user_cart, product=product, quantity=1)

    services.merge_carts(request, user)
    assert not Cart.objects.filter(pk=guest_cart.pk).exists()
    assert user_cart.items.get(product=product).quantity == 3
    assert "cart_id" not in request.session


def test_merge_attaches_cart_when_user_has_none(user, product):
    request = FakeRequest()
    guest_cart = services.get_or_create_cart(request)
    services.add_to_cart(request, product_id=product.pk, quantity=1)

    services.merge_carts(request, user)
    guest_cart.refresh_from_db()
    assert guest_cart.user == user
    assert guest_cart.session_key is None
    assert "cart_id" not in request.session


def test_quantity_update_clamps_to_stock(product):
    request = FakeRequest()
    services.add_to_cart(request, product_id=product.pk, quantity=1)
    item = CartItem.objects.first()
    services.update_item_quantity(request, item_id=item.pk, quantity=99)
    item.refresh_from_db()
    assert item.quantity == product.stock  # > stock → capped, the row stays


def test_quantity_update_of_missing_row_keeps_cart_page(client, product):
    # a row removed in another tab (or a double click) must not break the cart page
    response = client.post("/cart/htmx/item/999999/update/", {"quantity": 2})
    assert response.status_code == 200


def test_cart_changes_need_post(client, product):
    assert client.get(f"/cart/htmx/add/{product.pk}/").status_code == 405
    assert not CartItem.objects.exists()


def test_review_upsert_resets_approval(user, product, db):
    from apps.reviews.services import submit_review

    r1 = submit_review(user=user, product_id=product.pk, rating=4, body="good")
    r1.is_approved = True
    r1.save()
    submit_review(user=user, product_id=product.pk, rating=2, body="updated")
    assert r1.refresh_from_db() is None
    r1.refresh_from_db()
    assert r1.rating == 2
    assert r1.is_approved is False
