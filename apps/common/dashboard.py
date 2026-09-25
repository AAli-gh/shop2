from datetime import timedelta

from django.db.models import BigIntegerField, Count, Exists, ExpressionWrapper, F, OuterRef, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.catalog.models import Product, SearchTerm
from apps.orders.models import Order, OrderItem

PROFIT = ExpressionWrapper((F("unit_price") - F("unit_cost")) * F("quantity"), output_field=BigIntegerField())
STALE_DAYS = 60
COMPARE_DAYS = 30

PAID_STATUSES = [
    Order.Status.PAID,
    Order.Status.PROCESSING,
    Order.Status.SHIPPED,
    Order.Status.DELIVERED,
]


def _sold_items(since=None):
    """Order lines of orders that were actually paid for."""
    items = OrderItem.objects.filter(order__status__in=PAID_STATUSES)
    return items.filter(order__created_at__gte=since) if since else items


def profit_report(now=None):
    """Profit of the last 30 days and the products that earned it, from the cost price of each line."""
    now = now or timezone.now()
    since = now - timedelta(days=COMPARE_DAYS)
    priced = _sold_items(since).filter(unit_cost__isnull=False)
    totals = priced.aggregate(revenue=Sum("line_total"), profit=Sum(PROFIT))
    products = list(
        _sold_items(now - timedelta(days=90)).filter(unit_cost__isnull=False)
        .values("product_id", "product_name")
        .annotate(units=Sum("quantity"), revenue=Sum("line_total"), profit=Sum(PROFIT))
        .order_by("-profit")[:8]
    )
    return {
        "revenue": totals["revenue"] or 0,
        "profit": totals["profit"] or 0,
        # lines whose product has no cost price yet are missing from the numbers above
        "unpriced_lines": _sold_items(since).filter(unit_cost__isnull=True).count(),
        "products": products,
    }


def period_comparison(now=None):
    """The last 30 days against the 30 before them."""
    now = now or timezone.now()
    base = Order.objects.filter(status__in=PAID_STATUSES)

    def totals(start, end=None):
        rows = base.filter(created_at__gte=start)
        if end:
            rows = rows.filter(created_at__lt=end)
        row = rows.aggregate(total=Sum("total"), count=Count("id"))
        return {"total": row["total"] or 0, "count": row["count"] or 0}

    current = totals(now - timedelta(days=COMPARE_DAYS))
    previous = totals(now - timedelta(days=2 * COMPARE_DAYS), now - timedelta(days=COMPARE_DAYS))

    def change(new, old):
        if old:
            return round((new - old) * 100 / old)
        return 100 if new else 0

    return {
        "current": current,
        "previous": previous,
        "total_change": change(current["total"], previous["total"]),
        "count_change": change(current["count"], previous["count"]),
    }


def stale_products(now=None, limit=8):
    """In stock, on sale, but nothing sold in the last two months — money sitting on a shelf."""
    now = now or timezone.now()
    sold_recently = _sold_items(now - timedelta(days=STALE_DAYS)).filter(product=OuterRef("pk"))
    return list(
        Product.objects.filter(is_active=True, stock__gt=0)
        .filter(~Exists(sold_recently))
        .order_by("-stock")[:limit]
    )


def sales_stats():
    """Aggregates for the staff dashboard."""
    today = timezone.localdate()
    week_ago = today - timedelta(days=6)
    month_ago = today - timedelta(days=29)

    base = Order.objects.filter(status__in=PAID_STATUSES)

    def agg(qs):
        row = qs.aggregate(total=Sum("total"), count=Count("id"))
        return {"total": row["total"] or 0, "count": row["count"] or 0}

    daily_series = list(
        base.filter(created_at__date__gte=today - timedelta(days=13))
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Sum("total"), count=Count("id"))
        .order_by("day")
    )
    # fill missing days with zero so the chart has a continuous axis
    by_day = {row["day"]: row for row in daily_series}
    series = []
    for offset in range(13, -1, -1):
        d = today - timedelta(days=offset)
        row = by_day.get(d)
        series.append({"day": d, "total": row["total"] if row else 0, "count": row["count"] if row else 0})

    top_products = list(
        Product.objects.filter(is_active=True, sold_count__gt=0).order_by("-sold_count")[:8]
    )

    return {
        "today": agg(base.filter(created_at__date=today)),
        "week": agg(base.filter(created_at__date__gte=week_ago)),
        "month": agg(base.filter(created_at__date__gte=month_ago)),
        "pending_payment": Order.objects.filter(status=Order.Status.PENDING_PAYMENT).count(),
        "processing": Order.objects.filter(status__in=[Order.Status.PAID, Order.Status.PROCESSING]).count(),
        "shipped": Order.objects.filter(status=Order.Status.SHIPPED).count(),
        "cancelled": Order.objects.filter(status=Order.Status.CANCELLED).count(),
        "series": series,
        "top_products": top_products,
        "low_stock": list(
            Product.objects.filter(is_active=True, stock__lte=3).order_by("stock")[:8]
        ),
        "no_result_searches": list(
            SearchTerm.objects.filter(results_count=0, is_hidden=False).order_by("-count", "-last_searched_at")[:8]
        ),
        "comparison": period_comparison(),
        "profit": profit_report(),
        "stale_products": stale_products(),
    }
