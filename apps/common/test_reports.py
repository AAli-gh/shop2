from datetime import timedelta

import pytest
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product
from apps.common.dashboard import period_comparison, profit_report, sales_stats, stale_products
from apps.orders.models import Order
from apps.orders.services import place_order
from apps.payments.services import mark_paid

ADDRESS = {
    "full_name": "مریم احمدی", "phone": "09121234567", "province": "تهران",
    "city": "تهران", "postal_code": "1234567890", "address_line": "خیابان آزادی",
}


@pytest.fixture
def shop(db, django_user_model):
    category = Category.objects.create(name="یخچال", slug="fridge")
    priced = Product.objects.create(category=category, name="یخچال سودده", slug="priced",
                                    price=10_000_000, cost_price=7_000_000, stock=20)
    unpriced = Product.objects.create(category=category, name="یخچال بی‌قیمت‌خرید", slug="unpriced",
                                      price=5_000_000, stock=20)
    customer = django_user_model.objects.create_user(email="buyer@example.com", password="x")
    return priced, unpriced, customer


def buy(customer, product, quantity=1, days_ago=0, paid=True):
    cart, _ = Cart.objects.get_or_create(user=customer)
    cart.items.all().delete()
    CartItem.objects.create(cart=cart, product=product, quantity=quantity)
    order = place_order(user=customer, cart=cart, address_data=ADDRESS)
    if paid:
        mark_paid(order=order, ref=f"REF-{order.pk}")
    if days_ago:
        Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
    return order


def test_profit_uses_the_cost_price_of_each_line(shop):
    priced, unpriced, customer = shop
    buy(customer, priced, quantity=2)
    buy(customer, unpriced)

    report = profit_report()

    assert report["revenue"] == 20_000_000  # only lines that have a cost price
    assert report["profit"] == 6_000_000  # (10,000,000 - 7,000,000) × 2
    assert report["unpriced_lines"] == 1
    assert [row["product_name"] for row in report["products"]] == ["یخچال سودده"]


def test_the_cost_is_frozen_on_the_order_line(shop):
    priced, _, customer = shop
    buy(customer, priced)
    priced.cost_price = 9_500_000  # buying it again later costs more
    priced.save()

    assert profit_report()["profit"] == 3_000_000  # the old order keeps its old cost


def test_unpaid_orders_are_left_out(shop):
    priced, _, customer = shop
    buy(customer, priced, paid=False)
    assert profit_report()["profit"] == 0


def test_the_last_thirty_days_are_compared_with_the_thirty_before(shop):
    priced, _, customer = shop
    recent = buy(customer, priced, quantity=2)  # two units now
    earlier = buy(customer, priced, days_ago=40)  # one unit in the period before

    comparison = period_comparison()

    assert comparison["current"] == {"total": recent.total, "count": 1}
    assert comparison["previous"] == {"total": earlier.total, "count": 1}
    assert comparison["total_change"] == round((recent.total - earlier.total) * 100 / earlier.total)
    assert comparison["count_change"] == 0


def test_comparison_without_earlier_sales(shop):
    priced, _, customer = shop
    buy(customer, priced)
    assert period_comparison()["total_change"] == 100


def test_products_with_no_recent_sales_are_listed_as_stale(shop):
    priced, unpriced, customer = shop
    buy(customer, priced)  # sold today
    buy(customer, unpriced, days_ago=70)  # last sold more than two months ago

    stale = stale_products()

    assert [p.slug for p in stale] == ["unpriced"]

    Product.objects.filter(pk=unpriced.pk).update(stock=0)
    assert stale_products() == []  # nothing on the shelf, nothing to worry about


@pytest.mark.django_db
def test_the_dashboard_page_shows_the_new_reports(client, shop, django_user_model):
    priced, _, customer = shop
    buy(customer, priced, quantity=2)
    staff = django_user_model.objects.create_user(email="manager@example.com", password="x", is_staff=True,
                                                  is_superuser=True)
    client.force_login(staff)

    page = client.get("/dashboard/").content.decode()

    assert "سود ۳۰ روز اخیر" in page
    assert "مقایسه با دوره قبل" in page
    assert "کالاهای راکد" in page
    assert "۶,۰۰۰,۰۰۰" in page


def test_stats_include_every_report(shop):
    stats = sales_stats()
    assert {"comparison", "profit", "stale_products"} <= set(stats)
