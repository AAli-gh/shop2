import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.db import SessionStore

from apps.catalog.models import Category, Product
from apps.wishlist import services
from apps.wishlist.models import WishlistItem


class FakeRequest:
    def __init__(self, user):
        self.user = user
        self.session = SessionStore()
        self.session.create()


@pytest.fixture
def product(db):
    cat = Category.objects.create(name="c", slug="c")
    return Product.objects.create(category=cat, name="p", slug="p", price=10_000, stock=3)


@pytest.fixture
def user(db, django_user_model):
    return django_user_model.objects.create_user(email="wl@example.com", password="x")


def test_toggle_adds_then_removes(user, product):
    request = FakeRequest(user)
    result = services.toggle(request, product_id=product.pk)
    assert result["active"] is True
    assert result["count"] == 1
    assert WishlistItem.objects.filter(user=user, product=product).exists()

    result = services.toggle(request, product_id=product.pk)
    assert result["active"] is False
    assert result["count"] == 0
    assert not WishlistItem.objects.filter(user=user, product=product).exists()


def test_toggle_requires_login(product):
    request = FakeRequest(AnonymousUser())
    with pytest.raises(services.WishlistError):
        services.toggle(request, product_id=product.pk)


def test_toggle_rejects_inactive_product(user, product):
    product.is_active = False
    product.save()
    request = FakeRequest(user)
    with pytest.raises(services.WishlistError):
        services.toggle(request, product_id=product.pk)


def test_duplicate_product_for_user_is_blocked(user, product):
    WishlistItem.objects.create(user=user, product=product)
    with pytest.raises(Exception):
        WishlistItem.objects.create(user=user, product=product)


def test_count_and_list_for_user(user, product, db):
    cat = Category.objects.create(name="c2", slug="c2")
    p2 = Product.objects.create(category=cat, name="p2", slug="p2", price=5_000, stock=1)
    request = FakeRequest(user)
    services.toggle(request, product_id=product.pk)
    services.toggle(request, product_id=p2.pk)
    assert services.count_for(user) == 2
    assert {row.product.pk for row in services.wishlist_for(user)} == {product.pk, p2.pk}
