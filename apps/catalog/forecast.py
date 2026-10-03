"""When will stock run out? Sales speed of the last 30 days against what is on the shelf.

For every product (or colour/option of it) sold in the window: units per day, days until the shelf is
empty, and how many to order so the shop lasts the supplier's lead time plus a month. Products with no
recent sales can't be forecast; the dashboard lists those separately as stale stock.
"""
import math
from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone

WINDOW_DAYS = 30
COVER_DAYS = 30  # a reorder should last this long after it arrives
WARNING_DAYS = 14  # "soon": runs out within the lead time plus two weeks


class Status:
    OUT = "out"
    URGENT = "urgent"
    SOON = "soon"
    OK = "ok"


LABELS = {
    Status.OUT: "تمام شده",
    Status.URGENT: "فوری",
    Status.SOON: "به‌زودی",
    Status.OK: "کافی",
}


def stock_forecast(now=None, *, include_ok=False) -> dict:
    from apps.catalog.models import Product, ProductVariant
    from apps.common.services import get_settings
    from apps.orders.models import Order, OrderItem

    now = now or timezone.now()
    lead_days = get_settings().restock_lead_days
    sold = (
        OrderItem.objects.filter(
            order__status__in=[Order.Status.PAID, Order.Status.PROCESSING, Order.Status.SHIPPED, Order.Status.DELIVERED],
            order__created_at__gte=now - timedelta(days=WINDOW_DAYS),
            product__isnull=False,
        )
        .values("product_id", "variant_id")
        .annotate(units=Sum("quantity"))
    )
    sold = [row for row in sold if row["units"]]
    products = Product.objects.in_bulk({row["product_id"] for row in sold})
    variants = ProductVariant.objects.in_bulk({row["variant_id"] for row in sold if row["variant_id"]})

    rows = []
    for row in sold:
        product = products.get(row["product_id"])
        variant = variants.get(row["variant_id"]) if row["variant_id"] else None
        if product is None or not product.is_active or (row["variant_id"] and (variant is None or not variant.is_active)):
            continue
        stock = variant.stock if variant else product.stock
        per_day = row["units"] / WINDOW_DAYS
        days_left = stock / per_day
        if stock == 0:
            status = Status.OUT
        elif days_left <= lead_days:
            status = Status.URGENT
        elif days_left <= lead_days + WARNING_DAYS:
            status = Status.SOON
        else:
            status = Status.OK
        if status == Status.OK and not include_ok:
            continue
        rows.append({
            "product": product,
            "variant": variant,
            "stock": stock,
            "sold": row["units"],
            "per_day": round(per_day, 2),
            "days_left": math.floor(days_left),
            "runs_out_on": (now + timedelta(days=days_left)).date() if stock else now.date(),
            "reorder": max(0, math.ceil(per_day * (lead_days + COVER_DAYS)) - stock),
            "status": status,
            "status_label": LABELS[status],
        })
    rows.sort(key=lambda r: (r["days_left"], -r["sold"]))
    counts = {status: sum(1 for r in rows if r["status"] == status) for status in (Status.OUT, Status.URGENT, Status.SOON)}
    return {"rows": rows, "counts": counts, "lead_days": lead_days, "window_days": WINDOW_DAYS, "cover_days": COVER_DAYS}


def at_risk_count(now=None) -> int:
    """Sold recently and out of stock, or running out within the supplier's lead time."""
    counts = stock_forecast(now)["counts"]
    return counts[Status.OUT] + counts[Status.URGENT]
