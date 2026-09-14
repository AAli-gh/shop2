import json
import re

import pytest

from apps.blog.models import Post
from apps.catalog.models import Brand, Category, Product
from apps.common.models import SiteSettings
from apps.reviews.models import Review

LD_JSON = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def ld_blocks(response):
    return [json.loads(raw) for raw in LD_JSON.findall(response.content.decode())]


def one(response, schema_type):
    matches = [block for block in ld_blocks(response) if block.get("@type") == schema_type]
    assert len(matches) == 1, f"expected one {schema_type}, got {len(matches)}"
    return matches[0]


@pytest.fixture
def product(db):
    parent = Category.objects.create(name="لوازم خانگی", slug="home-appliances")
    fridges = Category.objects.create(name="یخچال و فریزر", slug="fridges", parent=parent)
    brand = Brand.objects.create(name="اسنوا", slug="snowa")
    return Product.objects.create(
        category=fridges, brand=brand, name="فریزر اسنوا ۵ کشو", slug="snowa-freezer",
        description="فریزر ایستاده", price=16_000_000, sale_price=14_500_000, stock=3,
    )


def test_product_rich_result(client, product):
    data = one(client.get(product.get_absolute_url()), "Product")
    assert data["name"] == product.name
    assert data["brand"] == {"@type": "Brand", "name": "اسنوا"}
    assert data["url"].startswith("http://testserver/product/")
    offer = data["offers"]
    assert offer["priceCurrency"] == "IRR"
    assert offer["price"] == 145_000_000  # sale price in Toman × 10
    assert offer["availability"] == "https://schema.org/InStock"
    assert "aggregateRating" not in data  # no approved reviews yet


def test_out_of_stock_product(client, product):
    product.stock = 0
    product.save()
    data = one(client.get(product.get_absolute_url()), "Product")
    assert data["offers"]["availability"] == "https://schema.org/OutOfStock"


def test_rating_counts_only_approved_reviews(client, product, django_user_model):
    Review.objects.create(product=product, user=django_user_model.objects.create_user(email="a@x.com", password="x"),
                          rating=4, body="خوب است", is_approved=True)
    Review.objects.create(product=product, user=django_user_model.objects.create_user(email="b@x.com", password="x"),
                          rating=1, body="در انتظار تأیید", is_approved=False)
    rating = one(client.get(product.get_absolute_url()), "Product")["aggregateRating"]
    assert (rating["ratingValue"], rating["reviewCount"]) == (4.0, 1)


def test_product_breadcrumb_follows_category_tree(client, product):
    crumbs = one(client.get(product.get_absolute_url()), "BreadcrumbList")["itemListElement"]
    assert [c["name"] for c in crumbs] == ["خانه", "لوازم خانگی", "یخچال و فریزر", product.name]
    assert [c["position"] for c in crumbs] == [1, 2, 3, 4]
    assert all(c["item"].startswith("http://testserver/") for c in crumbs)


def test_open_graph_price_is_in_rial(client, product):
    assert '<meta property="og:price:amount" content="145000000">' in client.get(product.get_absolute_url()).content.decode()


def test_product_name_cannot_break_out_of_the_script(client, product):
    product.name = 'فریزر </script><script>alert(1)</script>'
    product.save()
    response = client.get(product.get_absolute_url())
    assert "<script>alert(1)" not in response.content.decode()
    assert one(response, "Product")["name"] == product.name


def test_category_listing_breadcrumb(client, product):
    crumbs = one(client.get(product.category.get_absolute_url()), "BreadcrumbList")["itemListElement"]
    assert [c["name"] for c in crumbs] == ["خانه", "محصولات", "لوازم خانگی", "یخچال و فریزر"]


def test_home_describes_the_store(client, db):
    settings_obj = SiteSettings.load()
    settings_obj.store_name = "اعتماد"
    settings_obj.contact_phone = "021-88000000"
    settings_obj.save()
    response = client.get("/")
    store = one(response, "OnlineStore")
    assert store["name"] == "اعتماد"
    assert store["contactPoint"]["telephone"] == "021-88000000"
    assert one(response, "WebSite")["inLanguage"] == "fa-IR"


def test_blog_post_article(client, db):
    post = Post.objects.create(title="راهنمای خرید یخچال", slug="fridge-guide", excerpt="چه یخچالی بخریم؟",
                               body="متن راهنما", is_published=True)
    response = client.get(post.get_absolute_url())
    article = one(response, "BlogPosting")
    assert article["headline"] == "راهنمای خرید یخچال"
    assert article["datePublished"]
    assert [c["name"] for c in one(response, "BreadcrumbList")["itemListElement"]][-1] == "راهنمای خرید یخچال"
