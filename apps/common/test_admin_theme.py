import gettext
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.utils import translation

from apps.common.management.commands.compile_po import build_mo, parse_po
from apps.orders.models import Order, ReturnRequest
from apps.reviews.models import Review

PO_PATH = Path(settings.BASE_DIR) / "locale" / "fa" / "LC_MESSAGES" / "django.po"


def test_po_compiler_produces_a_readable_catalog(tmp_path):
    po = tmp_path / "django.po"
    po.write_text(
        'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
        'msgid "order"\nmsgstr "سفارش"\n\nmsgid "multi"\nmsgstr ""\n"یک "\n"دو"\n\nmsgid "untranslated"\nmsgstr ""\n',
        encoding="utf-8",
    )
    messages = parse_po(po.read_text(encoding="utf-8"))
    assert "untranslated" not in messages
    mo = tmp_path / "django.mo"
    mo.write_bytes(build_mo(messages))
    catalog = gettext.GNUTranslations(mo.open("rb"))
    assert catalog.gettext("order") == "سفارش"
    assert catalog.gettext("multi") == "یک دو"


def test_committed_mo_matches_the_po_file():
    """Guards against editing django.po without running `manage.py compile_po`."""
    messages = parse_po(PO_PATH.read_text(encoding="utf-8"))
    with translation.override("fa"):
        stale = [msgid for msgid, msgstr in messages.items() if msgid and translation.gettext(msgid) != msgstr]
    assert stale == []


def test_model_and_field_names_are_persian():
    with translation.override("fa"):
        assert str(Order._meta.verbose_name_plural) == "سفارش‌ها"
        assert str(Order._meta.get_field("order_number").verbose_name) == "شماره سفارش"
        assert str(ReturnRequest._meta.verbose_name) == "درخواست مرجوعی"


@pytest.mark.django_db
def test_admin_pages_use_the_theme(admin_client, client):
    assert "admin_theme/theme.css" in admin_client.get("/admin/").content.decode()
    assert "admin_theme/theme.css" in client.get("/admin/login/").content.decode()


@pytest.mark.django_db
def test_admin_home_shows_pending_work(admin_client, django_user_model):
    from apps.catalog.models import Category, Product

    product = Product.objects.create(category=Category.objects.create(name="c", slug="c"), name="p", slug="p",
                                     price=1000, stock=5)
    Review.objects.create(product=product, user=django_user_model.objects.create_user(email="r@x.com", password="x"),
                          rating=5, body="عالی بود", is_approved=False)

    body = admin_client.get("/admin/").content.decode()

    assert "نظر در انتظار تأیید" in body
    assert "/admin/reviews/review/?is_approved__exact=0" in body
    assert "dash-tasks__badge" in body  # the review counter is lit
    assert "سفارش‌ها" in body  # the menu groups are in Persian


@pytest.mark.django_db
def test_counters_respect_staff_permissions(client, django_user_model):
    from django.contrib.auth.models import Permission

    staff = django_user_model.objects.create_user(email="support@example.com", password="x", is_staff=True)
    staff.user_permissions.add(Permission.objects.get(codename="view_review"))
    client.force_login(staff)

    body = client.get("/admin/").content.decode()

    assert "نظر در انتظار تأیید" in body
    assert "آماده پردازش" not in body  # no order permission


# ---------------------------------------------------------------- shell and dashboard

@pytest.mark.django_db
def test_menu_shows_only_permitted_sections(client, django_user_model):
    from django.contrib.auth.models import Permission

    clerk = django_user_model.objects.create_user(email="warehouse@example.com", password="x", is_staff=True)
    clerk.user_permissions.add(Permission.objects.get(codename="view_product"))
    client.force_login(clerk)
    body = client.get("/admin/").content.decode()

    assert 'class="shop-nav"' in body and 'href="/admin/catalog/product/"' in body
    assert "/admin/orders/order/" not in body  # no orders section, card or table
    assert "/admin/accounts/user/" not in body
    assert "گزارش فروش" not in body  # no sales chart without order permission
    assert "وضعیت موجودی" in body


@pytest.mark.django_db
@pytest.mark.parametrize("days", ["7", "30", "90", "abc"])
def test_dashboard_with_sales(admin_client, django_user_model, days):
    from apps.catalog.models import Category, Product
    from apps.orders.models import Order, OrderItem

    product = Product.objects.create(category=Category.objects.create(name="یخچال", slug="c"), name="یخچال ساید",
                                     slug="p", price=1000, cost_price=700, stock=5)
    buyer = django_user_model.objects.create_user(email="b@x.com", password="x")
    order = Order.objects.create(order_number="SH-00000001", user=buyer, status=Order.Status.PAID, items_subtotal=2000, total=2000)
    OrderItem.objects.create(order=order, product=product, product_name=product.name, unit_price=1000, unit_cost=700,
                             quantity=2, line_total=2000)

    body = admin_client.get(f"/admin/?days={days}").content.decode()
    assert "گزارش فروش" in body and "<polyline" in body
    assert "سهم فروش بر اساس دسته‌بندی" in body and "یخچال" in body
    assert "SH-00000001" in body and "پرفروش‌ترین محصولات" in body


@pytest.mark.django_db
def test_admin_search(admin_client, django_user_model):
    from apps.catalog.models import Category, Product

    Product.objects.create(category=Category.objects.create(name="c", slug="c"), name="مایکروویو سامسونگ", slug="m", price=1, stock=1)
    django_user_model.objects.create_user(phone="09121112222", phone_verified=True, name="سارا")

    body = admin_client.get("/admin/search/", {"q": "مایکروویو"}).content.decode()
    assert "مایکروویو سامسونگ" in body
    assert "سارا" in admin_client.get("/admin/search/", {"q": "۰۹۱۲۱۱۱۲۲۲۲"}).content.decode()


@pytest.mark.django_db
def test_export_all_products(admin_client):
    response = admin_client.get("/admin/catalog/product/export/")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/vnd.openxmlformats")
