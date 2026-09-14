import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from io import BytesIO

from apps.catalog.importer import run_import
from apps.catalog.models import Category, Product
from apps.catalog.services import (
    best_sellers,
    featured_products,
    list_products,
    on_sale_products,
    price_bounds,
    related_products,
)

CSV_SAMPLE = (
    "name,price,category,slug,stock,sale_price,is_featured,description\n"
    "هدفون A,1200000,صوتی,a,5,990000,بله,توضیح الف\n"
    "هدفون B,800000,صوتی,b,2,,نه,\n"
    "کیف C,700000,کیف,c,0,,,\n"
)


@pytest.fixture
def products(db):
    cat1 = Category.objects.create(name="صوتی", slug="audio")
    cat2 = Category.objects.create(name="کیف", slug="bag")
    a = Product.objects.create(category=cat1, name="هدفون A", slug="a", price=990_000, stock=4, sold_count=12, is_featured=True)
    Product.objects.create(category=cat1, name="هدفون B", slug="b", price=800_000, stock=2, sold_count=30,
                           sale_price=700_000)
    Product.objects.create(category=cat2, name="کیف C", slug="c", price=700_000, stock=0)
    return a


def test_price_filter(db, products):
    page = list_products(min_price=800_000)
    assert all(p.price >= 800_000 for p in page.object_list)
    page = list_products(max_price=800_000)
    assert all(p.price <= 800_000 for p in page.object_list)


def test_price_bounds(db, products):
    lo, hi = price_bounds()
    assert lo == 700_000
    assert hi == 990_000


def test_best_sellers_order(db, products):
    names = [p.name for p in best_sellers()]
    assert names[0] == "هدفون B"


def test_on_sale_excludes_full_price(db, products):
    names = {p.name for p in on_sale_products()}
    assert names == {"هدفون B"}


def test_featured(db, products):
    names = {p.name for p in featured_products()}
    assert names == {"هدفون A"}


def test_related_excludes_self(db, products):
    names = {p.name for p in related_products(products)}
    assert "هدفون A" not in names
    assert "هدفون B" in names


def test_discount_properties(db):
    cat = Category.objects.create(name="c", slug="c")
    p = Product.objects.create(category=cat, name="x", slug="x", price=1_000, sale_price=750)
    assert p.discount_percent == 25
    assert p.effective_price == 750


def _csv(text):
    return BytesIO(text.encode("utf-8"))


def test_import_creates_products(db):
    report = run_import(_csv(CSV_SAMPLE), "p.csv", commit=True)
    assert report.created == 3
    assert report.errors == []
    p = Product.objects.get(slug="a")
    assert p.price == 1_200_000
    assert p.sale_price == 990_000
    assert p.is_featured is True
    assert p.category.name == "صوتی"
    assert Product.objects.get(slug="c").stock == 0


def test_import_updates_existing(db, products):
    report = run_import(_csv(CSV_SAMPLE), "p.csv", commit=True)
    assert report.created == 0
    assert report.updated == 3
    a = Product.objects.get(slug="a")
    assert a.price == 1_200_000
    assert a.sale_price == 990_000


def test_import_persian_digits_and_separators(db):
    report = run_import(_csv("name,price,category,stock\nدستی، ۲,۱۲۳٬۴۵۶,گ،,۳\n"), "fa.csv", commit=True)
    assert report.errors == []
    assert report.created == 1
    p = Product.objects.first()
    assert p.price == 123456
    assert p.stock == 3


def test_import_rejects_sale_ge_price(db):
    report = run_import(_csv("name,price,category,sale_price\nx,100,c,150\n"), "bad.csv", commit=True)
    assert report.created == 0
    assert len(report.errors) == 1
    assert "کمتر" in report.errors[0].message


def test_import_xlsx(db):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["name", "price", "category", "stock"])
    ws.append(["محصول اکسل", "500000", "گ", "7"])
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    f = SimpleUploadedFile("p.xlsx", buf.read())
    report = run_import(f, "p.xlsx", commit=True)
    assert report.created == 1
    assert Product.objects.get(slug="محصول-اکسل").stock == 7
