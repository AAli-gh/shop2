import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from io import BytesIO

from apps.catalog.importer import import_products
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


def test_import_creates_products(db):
    f = SimpleUploadedFile("p.csv", CSV_SAMPLE.encode("utf-8"))
    result = import_products(BytesIO(f.read()), "p.csv")
    assert result["created"] == 3
    assert result["errors"] == []
    p = Product.objects.get(slug="a")
    assert p.price == 1_200_000
    assert p.sale_price == 990_000
    assert p.is_featured is True
    assert p.category.name == "صوتی"
    assert Product.objects.get(slug="c").stock == 0


def test_import_updates_existing(db, products):
    f = SimpleUploadedFile("p.csv", CSV_SAMPLE.encode("utf-8"))
    result = import_products(BytesIO(f.read()), "p.csv")
    assert result["created"] == 0
    assert result["updated"] == 3
    a = Product.objects.get(slug="a")
    assert a.price == 1_200_000
    assert a.sale_price == 990_000


def test_import_persian_digits_and_separators(db):
    csv_data = "name,price,category,stock\nدستی، ۲,۱۲۳٬۴۵۶,گ،,۳\n"
    f = SimpleUploadedFile("fa.csv", csv_data.encode("utf-8"))
    result = import_products(BytesIO(f.read()), "fa.csv")
    assert result["errors"] == []
    assert result["created"] == 1
    p = Product.objects.first()
    assert p.price == 123456
    assert p.stock == 3


def test_import_rejects_sale_ge_price(db):
    csv_data = "name,price,category,sale_price\nx,100,c,150\n"
    f = SimpleUploadedFile("bad.csv", csv_data.encode("utf-8"))
    result = import_products(BytesIO(f.read()), "bad.csv")
    assert result["created"] == 0
    assert len(result["errors"]) == 1
    assert "کمتر" in result["errors"][0]["error"]


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
    result = import_products(f, "p.xlsx")
    assert result["created"] == 1
    assert Product.objects.get(slug="محصول-اکسل").stock == 7
