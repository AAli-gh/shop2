"""Win-back campaign: a personal discount code for customers who stopped buying.

Once a customer's last order is older than winback_after_days they get one offer — by SMS to a
verified mobile, otherwise by email to a verified address — and no other until they buy again.
The code is a one-use coupon that only their account can redeem. Customers who switched offers
off in their profile, staff and inactive accounts are never contacted. Runs from the scheduled
`send_winback` command, only while the campaign is switched on in site settings.
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q, Subquery
from django.template.loader import render_to_string
from django.utils import timezone

from apps.common.services import get_settings

MAX_PER_RUN = 100  # a first run on an old shop shouldn't text everyone at once
CODE_PREFIX = "BACK-"


def candidates(now=None):
    """Customers due an offer, longest asleep first; each row carries `last_order`."""
    from apps.crm.models import WinBackMessage
    from apps.crm.segments import paid_statuses
    from apps.orders.models import Order

    now = now or timezone.now()
    cutoff = now - timedelta(days=get_settings().winback_after_days)
    last_order = (
        Order.objects.filter(user=OuterRef("pk")).exclude(status=Order.Status.CANCELLED)
        .order_by("-created_at").values("created_at")[:1]
    )
    return (
        get_user_model().objects.filter(is_active=True, is_staff=False, accepts_marketing=True)
        .filter(Q(phone_verified=True, phone__isnull=False) | Q(email_verified=True, email__isnull=False))
        .filter(Exists(Order.objects.filter(user=OuterRef("pk"), status__in=paid_statuses())))
        .annotate(last_order=Subquery(last_order))
        .filter(last_order__lt=cutoff)
        # one offer per quiet spell: nothing sent since that last order
        .exclude(Exists(WinBackMessage.objects.filter(user=OuterRef("pk"), sent_at__gte=OuterRef("last_order"))))
        .order_by("last_order")
    )


def _new_coupon(user, now, shop):
    from apps.discounts.models import Coupon
    from apps.loyalty.models import new_referral_code

    for _ in range(5):
        try:
            with transaction.atomic():
                return Coupon.objects.create(
                    code=CODE_PREFIX + new_referral_code(),
                    kind=Coupon.Kind.PERCENT,
                    value=shop.winback_percent,
                    max_discount_amount=shop.winback_max_discount,
                    valid_from=now,
                    valid_to=now + timedelta(days=shop.winback_valid_days),
                    usage_limit=1,
                    per_user_limit=1,
                    owner=user,
                )
        except IntegrityError:
            continue  # the random code was taken
    return None


def offer_text(shop, coupon) -> str:
    cap = f" (تا سقف {shop.winback_max_discount:,} تومان)" if shop.winback_max_discount else ""
    return (
        f"{shop.store_name}: دلمان برایتان تنگ شده! با کد {coupon.code} "
        f"{shop.winback_percent}٪ تخفیف{cap} تا {shop.winback_valid_days} روز برای خرید بعدی شما فعال است. "
        f"{settings.SITE_URL.rstrip('/')}"
    )


def send_offer(user, *, now=None) -> bool:
    """Create the personal code and send it; False (and no code left behind) when nothing could go out."""
    from apps.common import sms
    from apps.crm.models import WinBackMessage

    now = now or timezone.now()
    shop = get_settings()
    coupon = _new_coupon(user, now, shop)
    if coupon is None:
        return False
    text = offer_text(shop, coupon)
    if user.phone and user.phone_verified:
        channel = WinBackMessage.Channel.SMS
        sent = sms.notify(user.phone, text, event="winback", params={
            "CODE": coupon.code, "PERCENT": shop.winback_percent, "DAYS": shop.winback_valid_days,
        })
    else:
        channel = WinBackMessage.Channel.EMAIL
        body = render_to_string("crm/emails/winback.txt", {"user": user, "text": text, "shop": shop, "coupon": coupon})
        sent = bool(send_mail(f"هدیه‌ای از {shop.store_name}", body, settings.DEFAULT_FROM_EMAIL, [user.email],
                              fail_silently=True))
    if not sent:
        coupon.delete()
        return False
    WinBackMessage.objects.create(
        user=user, coupon=coupon, channel=channel, sent_at=now,
        last_purchase_at=getattr(user, "last_order", None) or now,
    )
    return True


def send_winback(*, now=None, limit=MAX_PER_RUN) -> int:
    if not get_settings().winback_enabled:
        return 0
    return sum(1 for user in candidates(now)[:limit] if send_offer(user, now=now))


def campaign_stats(now=None) -> dict:
    """How the campaign is doing: offers sent, codes used, customers who came back and what they spent."""
    from apps.crm.models import WinBackMessage
    from apps.crm.segments import paid_statuses
    from apps.orders.models import Order
    from django.db.models import Sum

    now = now or timezone.now()
    messages = WinBackMessage.objects.all()
    with_code = Order.objects.filter(coupon__in=messages.values("coupon"), status__in=paid_statuses())
    came_back = messages.filter(Exists(Order.objects.filter(
        user=OuterRef("user"), status__in=paid_statuses(), created_at__gt=OuterRef("sent_at"),
    )))
    sent = messages.count()
    returned = came_back.values("user").distinct().count()
    return {
        "sent": sent,
        "sent_30_days": messages.filter(sent_at__gte=now - timedelta(days=30)).count(),
        "codes_used": with_code.count(),
        "revenue": with_code.aggregate(total=Sum("total"))["total"] or 0,
        "returned": returned,
        "return_rate": round(returned * 100 / sent) if sent else 0,
        "due_now": candidates(now).count(),
    }
