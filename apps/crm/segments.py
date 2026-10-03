"""Customer segments by buying habit (a light RFM): who is loyal, active, slipping away or asleep.

Built from paid orders only. The «asleep» line is the win-back setting (winback_after_days), so the
report and the campaign always agree on who counts as inactive.
"""
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db.models import Count, Exists, Max, OuterRef, Sum
from django.utils import timezone

ACTIVE_DAYS = 60
LOYAL_ORDERS = 3


@dataclass(frozen=True)
class Segment:
    key: str
    label: str
    description: str


LOYAL = Segment("loyal", "وفادار", f"دست‌کم {LOYAL_ORDERS} خرید و هنوز فعال")
ACTIVE = Segment("active", "فعال", f"خرید در {ACTIVE_DAYS} روز اخیر")
AT_RISK = Segment("at_risk", "در حال رفتن", "مدتی است خرید نکرده؛ هنوز خوابیده حساب نمی‌شود")
DORMANT = Segment("dormant", "خوابیده", "از آخرین خرید بیش از حد تعیین‌شده گذشته")
SEGMENTS = (LOYAL, ACTIVE, AT_RISK, DORMANT)
BY_KEY = {segment.key: segment for segment in SEGMENTS}


def paid_statuses():
    from apps.orders.models import Order

    return [Order.Status.PAID, Order.Status.PROCESSING, Order.Status.SHIPPED, Order.Status.DELIVERED]


def segment_for(*, orders: int, last_purchase, now, dormant_days: int) -> Segment:
    days = (now - last_purchase).days
    if days > dormant_days:
        return DORMANT
    if orders >= LOYAL_ORDERS:
        return LOYAL
    if days <= ACTIVE_DAYS:
        return ACTIVE
    return AT_RISK


def _customer_rows():
    from apps.orders.models import Order

    return (
        Order.objects.filter(status__in=paid_statuses())
        .values("user_id")
        .annotate(orders=Count("id"), spent=Sum("total"), last_purchase=Max("created_at"))
    )


def segments_report(*, segment: str = "", now=None, limit: int = 100) -> dict:
    from apps.common.services import get_settings
    from apps.crm.models import WinBackMessage
    from apps.orders.models import Order

    now = now or timezone.now()
    dormant_days = get_settings().winback_after_days
    summary = {s.key: {"segment": s, "customers": 0, "spent": 0} for s in SEGMENTS}
    chosen = []
    for row in _customer_rows():
        found = segment_for(orders=row["orders"], last_purchase=row["last_purchase"], now=now, dormant_days=dormant_days)
        summary[found.key]["customers"] += 1
        summary[found.key]["spent"] += row["spent"] or 0
        if found.key == segment:
            chosen.append(row)

    chosen.sort(key=lambda row: -(row["spent"] or 0))
    chosen = chosen[:limit]
    users = get_user_model().objects.in_bulk([row["user_id"] for row in chosen])
    last_offer = {}
    for message in WinBackMessage.objects.filter(user_id__in=users).order_by("sent_at"):
        last_offer[message.user_id] = message
    customers = [
        {**row, "user": users[row["user_id"]], "days": (now - row["last_purchase"]).days, "offer": last_offer.get(row["user_id"])}
        for row in chosen if row["user_id"] in users
    ]
    total = sum(item["customers"] for item in summary.values())
    never_bought = (
        get_user_model().objects.filter(is_active=True, is_staff=False)
        .exclude(Exists(Order.objects.filter(user=OuterRef("pk"), status__in=paid_statuses())))
        .count()
    )
    return {
        "summary": [
            {**item, "share": round(item["customers"] * 100 / total) if total else 0}
            for item in summary.values()
        ],
        "selected": BY_KEY.get(segment),
        "customers": customers,
        "total": total,
        "never_bought": never_bought,
        "dormant_days": dormant_days,
        "active_days": ACTIVE_DAYS,
        "loyal_orders": LOYAL_ORDERS,
    }
