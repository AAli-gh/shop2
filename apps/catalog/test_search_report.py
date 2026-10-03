from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission
from django.utils import timezone

from apps.catalog import search_report, services
from apps.catalog.models import Category, Product, SearchSynonym, SearchTerm


@pytest.fixture
def catalog(db):
    cat = Category.objects.create(name="لوازم آشپزخانه", slug="kitchen")
    Product.objects.create(category=cat, name="مایکروویو سامسونگ ۲۸ لیتری", slug="mw", price=100, stock=2)
    Product.objects.create(category=cat, name="ماشین ظرفشویی بوش", slug="dw", price=100, stock=2)
    return cat


def _missed(display, count=3, days_ago=1):
    return SearchTerm.objects.create(
        term=display, display=display, count=count, results_count=0,
        last_searched_at=timezone.now() - timedelta(days=days_ago),
    )


# ---------------------------------------------------------------- synonyms

def test_synonym_word_is_searched_as_the_shop_word(catalog):
    assert services.search_count("ماکروفر") == 0
    SearchSynonym.objects.create(term="ماكروفر", replacement="مایکروویو")  # typed with an Arabic kaf
    assert services.search_count("ماکروفر سامسونگ") == 1
    assert [p.slug for p in services.quick_search("ماکروفر")] == ["mw"]


def test_whole_phrase_synonym(catalog):
    SearchSynonym.objects.create(term="ماشین ظرف", replacement="ظرفشویی")
    assert services.search_count("ماشین ظرف") == 1


def test_synonym_change_applies_immediately(catalog):
    synonym = SearchSynonym.objects.create(term="ماکروفر", replacement="مایکروویو")
    assert services.search_count("ماکروفر") == 1
    synonym.delete()
    assert services.search_count("ماکروفر") == 0


def test_product_list_uses_synonyms(client, catalog):
    SearchSynonym.objects.create(term="ماکروفر", replacement="مایکروویو")
    page = client.get("/products/", {"q": "ماکروفر"}).content.decode()
    assert "مایکروویو سامسونگ" in page


# ---------------------------------------------------------------- report

def test_report_lists_recent_missed_searches_most_searched_first(catalog):
    _missed("کولر گازی", count=9)
    _missed("پنکه", count=4)
    _missed("بخاری", count=20, days_ago=200)  # too old
    SearchTerm.objects.create(term="یخچال", display="یخچال", count=50, results_count=3, last_searched_at=timezone.now())
    dismissed = _missed("قهوه", count=30)
    SearchTerm.objects.filter(pk=dismissed.pk).update(dismissed=True)

    rows = search_report.missed_searches()
    assert [row["term"].display for row in rows] == ["کولر گازی", "پنکه"]
    assert search_report.missed_count() == 2


def test_a_search_that_finds_products_now_resolves_itself(catalog):
    term = _missed("ماکروفر")
    SearchSynonym.objects.create(term="ماکروفر", replacement="مایکروویو")

    rows = search_report.missed_searches()
    assert rows[0]["found_now"] == 1
    term.refresh_from_db()
    assert term.results_count == 1
    assert search_report.missed_count() == 0


def test_close_catalog_words_are_suggested(catalog):
    _missed("مایکروفو")
    rows = search_report.missed_searches()
    assert "مایکروویو" in " ".join(rows[0]["suggestions"])


# ---------------------------------------------------------------- staff page

def test_staff_page_adds_a_synonym_and_dismisses(admin_client, catalog):
    ask = _missed("ماکروفر")
    fan = _missed("پنکه")
    assert admin_client.get("/dashboard/searches/").status_code == 200

    admin_client.post("/dashboard/searches/", {"term_id": ask.pk, "replacement": "مایکروویو"})
    assert services.search_count("ماکروفر") == 1

    admin_client.post("/dashboard/searches/", {"term_id": fan.pk, "action": "dismiss"})
    fan.refresh_from_db()
    assert fan.dismissed


def test_staff_page_needs_permissions(client, django_user_model, catalog):
    clerk = django_user_model.objects.create_user(email="clerk@example.com", password="x", is_staff=True)
    client.force_login(clerk)
    assert client.get("/dashboard/searches/").status_code == 403

    clerk.user_permissions.add(Permission.objects.get(codename="view_searchterm"))
    term = _missed("ماکروفر")
    assert client.get("/dashboard/searches/").status_code == 200
    assert client.post("/dashboard/searches/", {"term_id": term.pk, "replacement": "مایکروویو"}).status_code == 403
    assert not SearchSynonym.objects.exists()
