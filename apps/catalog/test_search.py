import pytest

from apps.catalog import services
from apps.catalog.models import Brand, Category, Product
from apps.common.text import normalize_search


@pytest.mark.parametrize(
    "raw, folded",
    [
        ("يخچال", "یخچال"),              # Arabic yeh
        ("كولر", "کولر"),                # Arabic kaf
        ("کم‌مصرف", "کم مصرف"),          # half-space
        ("۵ کشو", "5 کشو"),              # Persian digits
        ("٤ درب", "4 درب"),              # Arabic-Indic digits
        ("  LG   OLED ", "lg oled"),       # case + spacing
        ("آبمیوه‌گیری", "ابمیوه گیری"),  # alef-madda folded too
    ],
)
def test_normalize_search(raw, folded):
    assert normalize_search(raw) == folded


@pytest.fixture
def catalog(db):
    fridges = Category.objects.create(name="یخچال و فریزر", slug="fridges")
    samsung = Brand.objects.create(name="سامسونگ", slug="samsung")
    # typed on an Arabic keyboard, with a half-space
    side_by_side = Product.objects.create(
        category=fridges, brand=samsung, name="يخچال ساید باي ساید كم‌مصرف", slug="sbs", price=100,
    )
    freezer = Product.objects.create(category=fridges, name="فریزر ۵ کشو", slug="freezer", price=100)
    return {"fridges": fridges, "samsung": samsung, "sbs": side_by_side, "freezer": freezer}


def names(page_or_list):
    return {p.name for p in page_or_list}


@pytest.mark.parametrize(
    "query",
    ["یخچال کم مصرف", "يخچال", "کم‌مصرف", "ساید سامسونگ", "سامسونگ یخچال"],
)
def test_arabic_keyboard_product_is_found_by_any_spelling(catalog, query):
    assert catalog["sbs"].name in names(services.list_products(q=query))


@pytest.mark.parametrize("query", ["5 کشو", "۵ کشو", "كشو"])
def test_digits_match_in_either_script(catalog, query):
    assert names(services.list_products(q=query)) == {catalog["freezer"].name}


def test_all_words_must_match(catalog):
    # «کشو» is only in the freezer and «سامسونگ» only on the side-by-side: no product has both
    assert names(services.list_products(q="کشو سامسونگ")) == set()


def test_category_name_is_searchable(catalog):
    assert names(services.list_products(q="فريزر")) == {catalog["sbs"].name, catalog["freezer"].name}


def test_renaming_a_brand_updates_search(catalog):
    brand = catalog["samsung"]
    brand.name = "سامسونگ الکترونیک"
    brand.save()
    assert catalog["sbs"].name in names(services.list_products(q="الکترونيک"))


def test_partial_save_still_refreshes_search_text(catalog):
    product = catalog["freezer"]
    product.name = "فریزر افقی"
    product.save(update_fields=["name"])
    assert names(services.list_products(q="افقي")) == {"فریزر افقی"}


def test_live_search_uses_the_same_folding(catalog, client):
    assert names(services.quick_search("كشو")) == {catalog["freezer"].name}
    assert services.quick_search("ي") == []  # still needs two characters
    resp = client.get("/search/live/", {"q": "يخچال كم"})
    assert catalog["sbs"].name in resp.content.decode()


def test_product_list_page_finds_arabic_spelling(catalog, client):
    resp = client.get("/products/", {"q": "کم مصرف"})
    assert catalog["sbs"].name in resp.content.decode()
