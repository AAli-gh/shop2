from datetime import timedelta

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.catalog.models import Product
from apps.orders.models import Order

PAID_STATUSES = [
    Order.Status.PAID,
    Order.Status.PROCESSING,
    Order.Status.SHIPPED,
    Order.Status.DELIVERED,
]


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
    }
