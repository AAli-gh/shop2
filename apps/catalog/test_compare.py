import pytest
from django.urls import reverse

from apps.catalog import compare
from apps.catalog.models import Category, Product


@pytest.fixture
def products(db):
    cat = Category.objects.create(name="c", slug="c")
    return [Product.objects.create(category=cat, name=f"p{i}", slug=f"p{i}", price=100) for i in range(4)]


def _toggle(client, slug):
    return client.post(reverse("catalog:compare_toggle", args=[slug]))


def test_hidden_product_does_not_block_the_comparison(client, products):
    for p in products[:3]:
        _toggle(client, p.slug)
    Product.objects.filter(pk=products[0].pk).update(is_active=False)

    _toggle(client, products[3].slug)
    assert client.session[compare.SESSION_KEY] == ["p1", "p2", "p3"]


def test_unknown_slug_is_not_added(client, products):
    _toggle(client, "no-such-product")
    assert client.session.get(compare.SESSION_KEY, []) == []


def test_compare_changes_need_post(client, products):
    assert client.get(reverse("catalog:compare_toggle", args=["p0"])).status_code == 405
