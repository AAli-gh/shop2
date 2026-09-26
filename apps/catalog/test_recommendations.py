import pytest

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product
from apps.catalog.recommendations import bought_together, bought_together_with_cart
from apps.orders.services import place_order
from apps.payments.services import mark_paid

ADDRESS = {
    "full_name": "مریم احمدی", "phone": "09121234567", "province": "تهران",
    "city": "تهران", "postal_code": "1234567890", "address_line": "خیابان آزادی",
}


@pytest.fixture
def shop(db, django_user_model):
    category = Category.objects.create(name="یخچال", slug="fridge")
    fridge = Product.objects.create(category=category, name="یخچال ساید", slug="fridge-side", price=50_000_000, stock=20)
    guard = Product.objects.create(category=category, name="محافظ برق", slug="guard", price=900_000, stock=20)
    filter_ = Product.objects.create(category=category, name="فیلتر آب", slug="filter", price=1_500_000, stock=20)
    lonely = Product.objects.create(category=category, name="همزن", slug="mixer", price=2_000_000, stock=20)
    customer = django_user_model.objects.create_user(email="buyer@example.com", password="x")
    return fridge, guard, filter_, lonely, customer


def buy(customer, products, paid=True):
    cart, _ = Cart.objects.get_or_create(user=customer)
    cart.items.all().delete()
    for product in products:
        CartItem.objects.create(cart=cart, product=product, quantity=1)
    order = place_order(user=customer, cart=cart, address_data=ADDRESS)
    if paid:
        mark_paid(order=order, ref=f"REF-{order.pk}")
    return order


def test_companions_come_from_orders_that_held_both(shop):
    fridge, guard, filter_, lonely, customer = shop
    buy(customer, [fridge, guard])
    buy(customer, [fridge, guard])
    buy(customer, [fridge, filter_])

    companions = bought_together(fridge)

    assert [p.slug for p in companions] == ["guard", "filter"]  # the more frequent pair first
    assert lonely not in companions


def test_nothing_is_suggested_without_shared_orders(shop):
    fridge, _, _, lonely, customer = shop
    buy(customer, [fridge])
    assert bought_together(lonely) == []
    assert bought_together(fridge) == []


def test_unpaid_orders_teach_nothing(shop):
    fridge, guard, _, _, customer = shop
    buy(customer, [fridge, guard], paid=False)
    assert bought_together(fridge) == []


def test_sold_out_or_hidden_companions_are_left_out(shop):
    fridge, guard, filter_, _, customer = shop
    buy(customer, [fridge, guard])
    buy(customer, [fridge, filter_])
    Product.objects.filter(pk=guard.pk).update(stock=0)
    Product.objects.filter(pk=filter_.pk).update(is_active=False)

    assert bought_together(fridge) == []


def test_the_cart_suggests_companions_of_everything_in_it(shop):
    fridge, guard, filter_, lonely, customer = shop
    buy(customer, [fridge, guard])
    cart = Cart.objects.create(user=None, session_key="visitor-1")
    CartItem.objects.create(cart=cart, product=fridge, quantity=1)

    assert [p.slug for p in bought_together_with_cart(cart)] == ["guard"]

    CartItem.objects.create(cart=cart, product=guard, quantity=1)
    assert bought_together_with_cart(cart) == []  # already in the cart


def test_an_empty_cart_suggests_nothing(shop):
    cart = Cart.objects.create(session_key="visitor-2")
    assert bought_together_with_cart(cart) == []


@pytest.mark.django_db
def test_the_pages_show_the_section(client, shop):
    fridge, guard, _, _, customer = shop
    buy(customer, [fridge, guard])

    page = client.get(fridge.get_absolute_url()).content.decode()
    assert "معمولاً با هم خریده می‌شوند" in page
    assert "محافظ برق" in page.split("معمولاً با هم خریده می‌شوند", 1)[1]

    client.post(f"/cart/htmx/add/{fridge.pk}/", {"quantity": 1})
    cart_page = client.get("/cart/").content.decode()
    assert "مشتری‌ها این‌ها را با هم می‌خرند" in cart_page
    assert "محافظ برق" in cart_page


@pytest.mark.django_db
def test_a_product_without_companions_shows_no_section(client, shop):
    _, _, _, lonely, _ = shop
    assert "معمولاً با هم خریده می‌شوند" not in client.get(lonely.get_absolute_url()).content.decode()
