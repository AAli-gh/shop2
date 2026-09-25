import pytest
from django.utils import timezone

from apps.catalog.models import Brand, Category, Product, SearchTerm
from apps.catalog.search_suggest import suggest
from apps.catalog.services import list_products, personalized_products


@pytest.fixture
def catalog(db):
    fridges = Category.objects.create(name="یخچال و فریزر", slug="fridge")
    kitchen = Category.objects.create(name="لوازم آشپزخانه", slug="kitchen")
    samsung = Brand.objects.create(name="سامسونگ", slug="samsung")
    popular = Product.objects.create(category=fridges, brand=samsung, name="یخچال ساید سامسونگ", slug="side",
                                     price=50_000_000, stock=5, sold_count=30)
    quiet = Product.objects.create(category=fridges, name="فریزر کم‌صدا", slug="freezer", price=30_000_000,
                                   stock=3, sold_count=2, description="یخچال و فریزر خانگی")
    mixer = Product.objects.create(category=kitchen, name="همزن برقی", slug="mixer", price=2_000_000,
                                   stock=7, sold_count=9)
    return popular, quiet, mixer


# ---------------------------------------------------------------- ranking

def test_searches_put_the_best_match_and_best_seller_first(catalog):
    popular, quiet, _ = catalog

    results = list(list_products(q="یخچال").object_list)

    assert [p.slug for p in results] == ["side", "freezer"]  # name match beats a mention in the description


def test_the_customer_can_still_choose_another_order(catalog):
    results = list(list_products(q="یخچال", sort="price_asc").object_list)
    assert [p.slug for p in results] == ["freezer", "side"]


@pytest.mark.django_db
def test_the_search_page_offers_relevance_first(client, catalog):
    page = client.get("/products/", {"q": "یخچال"}).content.decode()
    assert '<option value="relevance" selected>مرتبط‌ترین</option>' in page.replace(" ", " ")


# ---------------------------------------------------------------- did you mean

def test_a_typo_is_matched_against_the_shop_vocabulary(catalog):
    assert "یخچال ساید سامسونگ" in suggest("یخچال ساید سامسونگ ") or suggest("یخچال ساید سامسونگ ") == []
    assert suggest("سامسونک") == ["سامسونگ"]
    assert suggest("همزن برقب")[0] in {"همزن برقی", "همزن"}


def test_nothing_is_suggested_for_gibberish(catalog):
    assert suggest("قثصثقهقثص") == []
    assert suggest("ی") == []


def test_earlier_fruitful_searches_join_the_vocabulary(catalog):
    SearchTerm.objects.create(term="ماشین ظرفشویی", display="ماشین ظرفشویی", count=5, results_count=3,
                              last_searched_at=timezone.now())
    assert suggest("ماشین ظرفشوی") == ["ماشین ظرفشویی"]


@pytest.mark.django_db
def test_a_fruitless_search_shows_suggestions_and_best_sellers(client, catalog):
    page = client.get("/products/", {"q": "سامسونک"}).content.decode()

    assert "نتیجه‌ای برای «سامسونک» پیدا نشد" in page
    assert "منظورتان" in page and "سامسونگ" in page
    assert "پرفروش‌ترین کالاها" in page and "یخچال ساید سامسونگ" in page


@pytest.mark.django_db
def test_the_live_search_dropdown_suggests_too(client, catalog):
    body = client.get("/search/live/", {"q": "سامسونک"}).content.decode()
    assert "منظورتان" in body and "سامسونگ" in body


@pytest.mark.django_db
def test_fruitless_searches_are_reported_to_staff(admin_client, catalog, client):
    client.get("/products/", {"q": "مایکروویو"})  # nothing found

    dashboard = admin_client.get("/dashboard/").content.decode()
    assert "جستجوهای بی‌نتیجه" in dashboard and "مایکروویو" in dashboard

    listing = admin_client.get("/admin/catalog/searchterm/?results=none").content.decode()
    assert "مایکروویو" in listing


# ---------------------------------------------------------------- personalized home

class _Request:
    def __init__(self, session, user=None):
        from django.contrib.auth.models import AnonymousUser

        self.session = session
        self.user = user or AnonymousUser()


@pytest.mark.django_db
def test_the_home_page_suggests_from_what_the_visitor_viewed(client, catalog):
    popular, quiet, mixer = catalog

    assert "پیشنهاد برای شما" not in client.get("/").content.decode()  # nothing seen yet

    client.get(quiet.get_absolute_url())
    page = client.get("/").content.decode()

    assert "پیشنهاد برای شما" in page
    section = page.split("پیشنهاد برای شما", 1)[1].split("</section>", 1)[0]
    assert "یخچال ساید سامسونگ" in section  # same category as the product just viewed
    assert "همزن برقی" not in section  # another category
    assert "فریزر کم‌صدا" not in section  # already seen


@pytest.mark.django_db
def test_past_purchases_count_too(client, catalog, django_user_model):
    from apps.cart.models import Cart, CartItem
    from apps.orders.services import place_order

    popular, _, mixer = catalog
    Product.objects.create(category=mixer.category, name="سرخ‌کن برقی", slug="fryer", price=3_000_000, stock=4)
    customer = django_user_model.objects.create_user(email="buyer@example.com", password="x")
    cart = Cart.objects.create(user=customer)
    CartItem.objects.create(cart=cart, product=mixer, quantity=1)
    place_order(user=customer, cart=cart, address_data={
        "full_name": "م", "phone": "09121234567", "province": "تهران",
        "city": "تهران", "postal_code": "1234567890", "address_line": "خ",
    })
    client.force_login(customer)

    page = client.get("/").content.decode()
    section = page.split("پیشنهاد برای شما", 1)[1].split("</section>", 1)[0]

    assert "سرخ‌کن برقی" in section  # same category as what they bought
    assert "همزن برقی" not in section  # the bought product itself is left out


@pytest.mark.django_db
def test_no_suggestions_without_history(client, catalog):
    from django.contrib.sessions.backends.db import SessionStore

    assert personalized_products(_Request(SessionStore())) == []
