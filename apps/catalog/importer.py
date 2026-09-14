"""Product import from CSV / Excel files.

Expected columns (header row, order-insensitive):
    name (required), price (required, Toman), category (required),
    slug (optional — auto from name), description, stock, sale_price, is_featured
Digits may be Persian; currency separators (, ؛ ,) are stripped.
Existing rows (matched by slug) are UPDATED.
"""
import csv
import io
import re

from django.utils.text import slugify

from apps.catalog.models import Category, Product

FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
SEP_RE = re.compile(r"[,،٬\s]")


def _to_int(value):
    if value is None:
        return None
    s = str(value).translate(FA_DIGITS)
    s = SEP_RE.sub("", s).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        raise ValueError(f"«{value}» عدد معتبر نیست")


def _to_bool(value):
    s = str(value or "").translate(FA_DIGITS).strip().lower()
    return s in {"1", "true", "yes", "y", "بله", "فعال", "true"}


def read_rows(file_obj, filename: str):
    """Yield dicts keyed by lowercase header for CSV or XLSX."""
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        import openpyxl

        wb = openpyxl.load_workbook(file_obj, read_only=True, data_only=True)
        ws = wb.active
        rows = ws.iter_rows(values_only=True)
        header = None
        for row in rows:
            cells = ["" if c is None else str(c).strip() for c in row]
            if header is None:
                header = [h.lower() for h in cells]
                continue
            if not any(cells):
                continue
            yield dict(zip(header, cells))
    else:
        data = file_obj.read()
        text = data.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            cleaned = { (k or "").strip().lower(): (v or "").strip() for k, v in row.items() }
            if any(cleaned.values()):
                yield cleaned


REQUIRED = {"name", "price", "category"}


def import_products(file_obj, filename: str) -> dict:
    """Import products; returns summary. Raises nothing — all row errors collected."""
    created, updated, errors = 0, 0, []
    rownum = 1  # header is row 1
    try:
        for raw in read_rows(file_obj, filename):
            rownum += 1
            row = {k.strip(): v for k, v in raw.items() if k}
            missing = REQUIRED - set(row)
            if missing:
                errors.append({"row": rownum, "error": f"ستون‌های الزامی غایب: {', '.join(sorted(missing))}"})
                continue
            name = row["name"].strip()
            if not name:
                errors.append({"row": rownum, "error": "نام محصول خالی است"})
                continue
            try:
                price = _to_int(row["price"])
                if price is None or price < 0:
                    raise ValueError("قیمت الزامی و ≥ ۰ است")
                stock = _to_int(row.get("stock")) or 0
                if stock < 0:
                    raise ValueError("موجودی نمی‌تواند منفی باشد")
                sale_price = _to_int(row.get("sale_price"))
                if sale_price is not None:
                    if sale_price <= 0:
                        raise ValueError("قیمت تخفیف باید مثبت باشد")
                    if sale_price >= price:
                        raise ValueError("قیمت تخفیف باید کمتر از قیمت اصلی باشد")
                category_name = row["category"].strip()
            except ValueError as exc:
                errors.append({"row": rownum, "error": str(exc), "name": name})
                continue

            category, _ = Category.objects.get_or_create(
                name=category_name, defaults={"slug": slugify(category_name, allow_unicode=True)}
            )
            slug = (row.get("slug") or "").strip() or slugify(name, allow_unicode=True)

            defaults = {
                "name": name,
                "price": price,
                "stock": stock,
                "sale_price": sale_price,
                "is_featured": _to_bool(row.get("is_featured")),
                "category": category,
            }
            if row.get("description"):
                defaults["description"] = row["description"]

            product, was_created = Product.objects.update_or_create(slug=slug, defaults=defaults)
            if was_created:
                created += 1
            else:
                updated += 1
    except (UnicodeDecodeError, KeyError) as exc:
        errors.append({"row": 0, "error": f"خواندن فایل ناموفق بود: {exc}"})

    return {"created": created, "updated": updated, "errors": errors}
