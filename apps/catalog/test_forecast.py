from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalog.forecast import Status, at_risk_count, stock_forecast
from apps.catalog.models import Category, Product, ProductVariant
from apps.common.models import SiteSettings
from apps.orders.models import Order, OrderItem

NOW = timezone.now()


@pytest.fixture(autouse=True)
def lead_time(db):
    s = SiteSettings.load()
    s.restock_lead_days = 7
    s.save()


@pytest.fixture
def buyer(django_user_model):
    return django_user_model.objects.create_user(email="f@example.com", password="x")


@pytest.fixture
def category(db):
    return Category.objects.create(name="c", slug="c")


def sell(buyer, product, units, *, days_ago=5, status=Order.Status.PAID, variant=None):
    order = Order.objects.create(
        order_number=f"SH-{Order.objects.count() + 1:08d}", user=buyer, status=status,
        items_subtotal=units * product.price, total=units * product.price,
    )
    Order.objects.filter(pk=order.pk).update(created_at=NOW - timedelta(days=days_ago))
    OrderItem.objects.create(order=order, product=product, variant=variant, product_name=product.name,
                             unit_price=product.price, quantity=units, line_total=units * product.price)


def row_for(product, **kwargs):
    return next(r for r in stock_forecast(NOW, include_ok=True, **kwargs)["rows"] if r["product"] == product)


def test_days_left_and_reorder_from_the_last_30_days(buyer, category):
    fridge = Product.objects.create(category=category, name="یخچال", slug="f", price=100, stock=5)
    sell(buyer, fridge, 30)  # one a day

    row = row_for(fridge)
    assert row["per_day"] == 1
    assert row["days_left"] == 5
    assert row["status"] == Status.URGENT  # gone before a 7-day delivery arrives
    assert row["reorder"] == 1 * (7 + 30) - 5


def test_statuses(buyer, category):
    out = Product.objects.create(category=category, name="a", slug="a", price=100, stock=0)
    soon = Product.objects.create(category=category, name="b", slug="b", price=100, stock=15)
    fine = Product.objects.create(category=category, name="c", slug="c", price=100, stock=500)
    for product in (out, soon, fine):
        sell(buyer, product, 30)

    result = stock_forecast(NOW)
    assert {r["product"].slug: r["status"] for r in result["rows"]} == {"a": Status.OUT, "b": Status.SOON}
    assert result["counts"] == {Status.OUT: 1, Status.URGENT: 0, Status.SOON: 1}
    assert at_risk_count(NOW) == 1


def test_only_paid_recent_sales_count(buyer, category):
    fridge = Product.objects.create(category=category, name="یخچال", slug="f", price=100, stock=5)
    sell(buyer, fridge, 100, status=Order.Status.CANCELLED)
    sell(buyer, fridge, 100, status=Order.Status.PENDING_PAYMENT)
    sell(buyer, fridge, 100, days_ago=45)
    assert stock_forecast(NOW, include_ok=True)["rows"] == []


def test_colour_variants_are_forecast_on_their_own_stock(buyer, category):
    fridge = Product.objects.create(category=category, name="یخچال", slug="f", price=100, stock=0)
    white = ProductVariant.objects.create(product=fridge, color_name="سفید", price=100, stock=2)
    steel = ProductVariant.objects.create(product=fridge, color_name="استیل", price=100, stock=90)
    sell(buyer, fridge, 15, variant=white)
    sell(buyer, fridge, 15, variant=steel)

    rows = {r["variant"].color_name: r for r in stock_forecast(NOW, include_ok=True)["rows"]}
    assert rows["سفید"]["status"] == Status.URGENT
    assert rows["استیل"]["status"] == Status.OK


def test_report_page_and_admin_card(admin_client, buyer, category):
    fridge = Product.objects.create(category=category, name="یخچال ساید", slug="f", price=100, stock=1)
    sell(buyer, fridge, 30)
    page = admin_client.get("/dashboard/stock/").content.decode()
    assert "یخچال ساید" in page
    assert "رو به اتمام" in admin_client.get("/admin/").content.decode()
