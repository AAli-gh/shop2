from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalog.models import Category, Product, SearchTerm
from apps.catalog.search_history import POPULAR_MIN_COUNT, popular_searches


@pytest.fixture
def catalog(db):
    fridges = Category.objects.create(name="یخچال و فریزر", slug="fridge")
    Product.objects.create(category=fridges, name="یخچال ساید سامسونگ", slug="side", price=50_000_000, stock=3)
    Product.objects.create(category=fridges, name="فریزر ال‌جی", slug="freezer", price=30_000_000, stock=2)
    return fridges


def _suggestions(client):
    return client.get("/search/live/", {"q": ""}).content.decode()


def test_the_search_box_asks_for_suggestions_when_focused(client, catalog):
    page = client.get("/").content.decode()
    assert 'hx-trigger="focus, click, input changed delay:300ms, search"' in page


def test_categories_are_offered_before_anything_was_searched(client, catalog):
    body = _suggestions(client)
    assert "دسته‌بندی‌ها" in body and "یخچال و فریزر" in body
    assert "جستجوهای اخیر شما" not in body


def test_submitted_searches_show_up_as_recent_newest_first(client, catalog):
    client.get("/products/", {"q": "یخچال"})
    client.get("/products/", {"q": "فریزر"})
    client.get("/products/", {"q": "يخچال"})  # Arabic ye: the same search, moved to the front

    body = _suggestions(client)

    assert "جستجوهای اخیر شما" in body
    assert body.index(">يخچال<") < body.index(">فریزر<")
    assert body.count(">یخچال<") + body.count(">يخچال<") == 1


def test_recent_searches_can_be_cleared(client, catalog):
    client.get("/products/", {"q": "یخچال"})
    body = client.post("/search/recent/clear/").content.decode()
    assert "جستجوهای اخیر شما" not in body
    assert "جستجوهای اخیر شما" not in _suggestions(client)


def test_each_visitor_counts_a_term_once(client, catalog):
    for page in ("1", "2", None):
        client.get("/products/", {"q": "یخچال", **({"page": page} if page else {})})
    assert SearchTerm.objects.get().count == 1


def test_popular_needs_several_visitors_and_real_results(client_factory, catalog):
    for _ in range(POPULAR_MIN_COUNT):
        client_factory().get("/products/", {"q": "یخچال"})
        client_factory().get("/products/", {"q": "ماشین زمان"})  # finds nothing
    client_factory().get("/products/", {"q": "فریزر"})  # only once

    assert popular_searches() == ["یخچال"]
    body = _suggestions(client_factory())
    assert "جستجوهای پرطرفدار" in body and ">یخچال<" in body
    assert "ماشین زمان" not in body and "دسته‌بندی‌ها" not in body


def test_staff_can_hide_a_popular_term(admin_client, catalog):
    SearchTerm.objects.create(term="یخچال", display="یخچال", count=9, results_count=2, last_searched_at=timezone.now())
    term = SearchTerm.objects.get()
    admin_client.post("/admin/catalog/searchterm/", {
        "form-TOTAL_FORMS": 1, "form-INITIAL_FORMS": 1, "form-MIN_NUM_FORMS": 0, "form-MAX_NUM_FORMS": 1000,
        "form-0-id": term.pk, "form-0-is_hidden": "on", "_save": "Save",
    })
    assert SearchTerm.objects.get().is_hidden
    assert popular_searches() == []


def test_old_terms_drop_out_of_popular(catalog):
    SearchTerm.objects.create(term="یخچال", display="یخچال", count=50, results_count=2,
                              last_searched_at=timezone.now() - timedelta(days=200))
    assert popular_searches() == []


def test_typing_still_shows_live_results(client, catalog):
    body = client.get("/search/live/", {"q": "ساید"}).content.decode()
    assert "یخچال ساید سامسونگ" in body


@pytest.fixture
def client_factory(db):
    from django.test import Client

    return Client
