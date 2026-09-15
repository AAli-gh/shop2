import io
import json
import re

import openpyxl
import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.db import SessionStore
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.cart import services as cart_services
from apps.cart.models import Cart, CartItem
from apps.catalog import importer
from apps.catalog.models import Category, Product, ProductVariant
from apps.catalog.stock import give_back_stock
from apps.common.sms import LocmemSmsBackend
from apps.orders.models import Order
from apps.orders.services import OrderError, cancel_pending_order, place_order

ADDRESS = {
    "full_name": "مریم احمدی", "phone": "09121234567", "province": "تهران",
    "city": "تهران", "postal_code": "1234567890", "address_line": "خیابان آزادی",
}


class FakeRequest:
    def __init__(self, user=None):
        self.session = SessionStore()
        self.session.create()
        self.user = user or AnonymousUser()


@pytest.fixture
def fridge(db):
    category = Category.objects.create(name="یخچال", slug="fridge")
    product = Product.objects.create(category=category, name="یخچال ساید", slug="side", price=1, stock=0)
    white = ProductVariant.objects.create(product=product, color_name="سفید", color_hex="#FFFFFF",
                                          price=50_000_000, stock=5, sort_order=1)
    steel = ProductVariant.objects.create(product=product, color_name="استیل", option="۲۴ فوت",
                                          price=60_000_000, sale_price=45_000_000, stock=2, sort_order=2)
    product.refresh_from_db()
    return product, white, steel


@pytest.fixture
def customer(django_user_model):
    return django_user_model.objects.create_user(email="buyer@example.com", password="x")


def test_product_mirrors_cheapest_price_and_total_stock(fridge):
    product, white, steel = fridge
    assert (product.price, product.sale_price, product.stock) == (60_000_000, 45_000_000, 7)
    assert product.has_variants
    assert steel.label == "استیل · ۲۴ فوت"

    steel.is_active = False
    steel.save()
    product.refresh_from_db()
    assert (product.price, product.sale_price, product.stock) == (50_000_000, None, 5)

    white.is_active = False
    white.save()
    product.refresh_from_db()
    assert product.stock == 0  # no sellable option left


def test_cart_needs_a_variant_of_this_product(fridge, db):
    product, white, steel = fridge
    other = Product.objects.create(category=product.category, name="x", slug="x", price=10, stock=3)
    other_variant = ProductVariant.objects.create(product=other, color_name="مشکی", price=10, stock=1)
    request = FakeRequest()

    with pytest.raises(cart_services.CartError):
        cart_services.add_to_cart(request, product_id=product.pk)
    with pytest.raises(cart_services.CartError):
        cart_services.add_to_cart(request, product_id=product.pk, variant_id=other_variant.pk)

    cart_services.add_to_cart(request, product_id=product.pk, variant_id=white.pk, quantity=9)
    summary = cart_services.add_to_cart(request, product_id=product.pk, variant_id=steel.pk)

    assert [(row["variant"], row["item"].quantity, row["unit_price"]) for row in summary["items"]] == [
        (white, 5, 50_000_000), (steel, 1, 45_000_000),
    ]
    assert summary["subtotal"] == 5 * 50_000_000 + 45_000_000


def test_order_takes_and_cancellation_returns_variant_stock(fridge, customer):
    product, white, steel = fridge
    cart = Cart.objects.create(user=customer)
    CartItem.objects.create(cart=cart, product=product, variant=steel, quantity=2)

    order = place_order(user=customer, cart=cart, address_data=ADDRESS)

    item = order.items.get()
    assert (item.variant, item.variant_label, item.unit_price) == (steel, "استیل · ۲۴ فوت", 45_000_000)
    assert item.product_name == "یخچال ساید — استیل · ۲۴ فوت"
    steel.refresh_from_db()
    product.refresh_from_db()
    assert steel.stock == 0
    assert (product.stock, product.sold_count, product.price) == (5, 2, 60_000_000)

    cancel_pending_order(order=order)

    steel.refresh_from_db()
    product.refresh_from_db()
    assert (steel.stock, product.stock, product.sold_count) == (2, 7, 0)


def test_cart_line_added_before_variants_existed_must_be_rechosen(fridge, customer):
    product, _, _ = fridge
    cart = Cart.objects.create(user=customer)
    CartItem.objects.create(cart=cart, product=product, quantity=1)

    with pytest.raises(OrderError) as exc:
        place_order(user=customer, cart=cart, address_data=ADDRESS)

    assert exc.value.code == "variant_required"
    assert not Order.objects.exists()


def test_selling_down_to_the_threshold_alerts_managers(fridge, customer, settings, django_capture_on_commit_callbacks):
    product, white, _ = fridge
    settings.ORDER_NOTIFY_PHONES = ["09350000000"]
    settings.LOW_STOCK_THRESHOLD = 3
    cart = Cart.objects.create(user=customer)
    CartItem.objects.create(cart=cart, product=product, variant=white, quantity=2)

    with django_capture_on_commit_callbacks(execute=True):
        place_order(user=customer, cart=cart, address_data=ADDRESS)

    alerts = [m["text"] for m in LocmemSmsBackend.outbox if m["phone"] == "09350000000"]
    assert len(alerts) == 1 and "کمبود موجودی" in alerts[0] and "سفید" in alerts[0]


def test_give_back_stock_for_a_deleted_variant_goes_to_the_product(db):
    category = Category.objects.create(name="c", slug="c")
    product = Product.objects.create(category=category, name="p", slug="p", price=10, stock=1, sold_count=3)
    give_back_stock(product_id=product.pk, variant_id=None, quantity=2)
    product.refresh_from_db()
    assert (product.stock, product.sold_count) == (3, 1)


@pytest.mark.django_db
def test_product_page_shows_the_chosen_variant(client, fridge):
    product, white, steel = fridge

    page = client.get(product.get_absolute_url()).content.decode()
    assert 'data-variant-picker' in page
    assert re.search(rf'value="{white.pk}"[^>]*\s+checked', page)  # first in stock
    assert "۵۰,۰۰۰,۰۰۰" in page

    page = client.get(f"{product.get_absolute_url()}?v={steel.pk}").content.decode()
    assert re.search(rf'value="{steel.pk}"[^>]*\s+checked', page)
    assert 'data-price>۴۵,۰۰۰,۰۰۰' in page


@pytest.mark.django_db
def test_card_links_to_the_page_instead_of_adding(client, fridge):
    product, _, _ = fridge
    listing = client.get("/products/").content.decode()
    assert f'href="{product.get_absolute_url()}" title="انتخاب مدل و خرید"' in listing
    assert f"/cart/htmx/add/{product.pk}/" not in listing


@pytest.mark.django_db
def test_htmx_add_posts_the_variant(client, fridge):
    product, _, steel = fridge
    response = client.post(f"/cart/htmx/add/{product.pk}/", {"quantity": 1, "variant": steel.pk})
    assert "به سبد اضافه شد" in response.content.decode()
    assert CartItem.objects.get().variant == steel


@pytest.mark.django_db
def test_admin_inline_edits_update_the_product(admin_client, fridge):
    product, white, steel = fridge
    url = f"/admin/catalog/product/{product.pk}/change/"
    page = admin_client.get(url)
    form = page.context["adminform"].form
    assert "price" not in form.fields and "stock" not in form.fields  # read-only, mirrored from variants

    data = {
        "name": product.name, "category": product.category.pk, "brand": "", "description": "", "video_url": "",
        "is_featured": "", "installment_months": 0, "installment_down_payment": 0, "country": "", "warranty": "",
        "energy_class": "", "weight_kg": "", "is_active": "on",
        "variants-TOTAL_FORMS": 2, "variants-INITIAL_FORMS": 2, "variants-MIN_NUM_FORMS": 0, "variants-MAX_NUM_FORMS": 1000,
        "variants-0-id": white.pk, "variants-0-product": product.pk, "variants-0-color_name": "سفید",
        "variants-0-color_hex": "#FFFFFF", "variants-0-option": "", "variants-0-sku": "", "variants-0-price": 40_000_000,
        "variants-0-sale_price": "", "variants-0-stock": 5, "variants-0-is_active": "on", "variants-0-sort_order": 1,
        "variants-1-id": steel.pk, "variants-1-product": product.pk, "variants-1-color_name": "استیل",
        "variants-1-color_hex": "", "variants-1-option": "۲۴ فوت", "variants-1-sku": "", "variants-1-price": 60_000_000,
        "variants-1-sale_price": 45_000_000, "variants-1-stock": 2, "variants-1-is_active": "on", "variants-1-sort_order": 2,
        "images-TOTAL_FORMS": 0, "images-INITIAL_FORMS": 0, "images-MIN_NUM_FORMS": 0, "images-MAX_NUM_FORMS": 1000,
        "attributes-TOTAL_FORMS": 0, "attributes-INITIAL_FORMS": 0, "attributes-MIN_NUM_FORMS": 0, "attributes-MAX_NUM_FORMS": 1000,
    }
    response = admin_client.post(url, data)

    assert response.status_code == 302, response.context["errors"] if response.context else response
    product.refresh_from_db()
    assert (product.price, product.sale_price, product.stock) == (40_000_000, None, 7)


def test_import_refuses_price_changes_on_variant_products_and_export_leaves_them_blank(fridge):
    product, _, _ = fridge
    workbook = openpyxl.Workbook()
    workbook.active.append(["شناسه", "قیمت"])
    workbook.active.append([product.slug, "1000"])
    buffer = io.BytesIO()
    workbook.save(buffer)

    report = importer.run_import(SimpleUploadedFile("p.xlsx", buffer.getvalue()), "p.xlsx", commit=True)
    assert "تنوع" in report.errors[0].message

    exported = openpyxl.load_workbook(io.BytesIO(importer.build_workbook(Product.objects.filter(pk=product.pk))))
    row = [cell.value for cell in exported["محصولات"][2]]
    columns = [c.key for c in importer.COLUMNS]
    assert row[columns.index("price")] is None and row[columns.index("stock")] is None


@pytest.mark.django_db
def test_structured_data_uses_an_aggregate_offer(client, fridge):
    product, _, _ = fridge
    page = client.get(product.get_absolute_url()).content.decode()
    blocks = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)]
    offers = next(b for b in blocks if b.get("@type") == "Product")["offers"]
    assert offers["@type"] == "AggregateOffer"
    assert (offers["lowPrice"], offers["highPrice"], offers["offerCount"]) == (450_000_000, 500_000_000, 2)
