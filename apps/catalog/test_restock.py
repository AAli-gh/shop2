import pytest

from apps.catalog.models import Category, Product, RestockNotification
from apps.catalog.restock import subscribe


@pytest.fixture
def product(db):
    cat = Category.objects.create(name="c", slug="c")
    return Product.objects.create(category=cat, name="p", slug="p", price=100, stock=0)


def test_subscribe_valid_email(product):
    result = subscribe(product=product, email="USER@example.com")
    assert result["ok"] is True
    req = RestockNotification.objects.get(product=product)
    assert req.email == "user@example.com"
    assert req.notified is False


def test_subscribe_rejects_bad_email(product):
    result = subscribe(product=product, email="not-an-email")
    assert result["ok"] is False
    assert not RestockNotification.objects.exists()


def test_subscribe_duplicate_is_idempotent(product):
    subscribe(product=product, email="a@b.com")
    subscribe(product=product, email="a@b.com")
    assert RestockNotification.objects.filter(email="a@b.com").count() == 1
