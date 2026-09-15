"""Abandoned-cart reminders: one SMS to a signed-in customer who left items in the cart without ordering."""
from datetime import timedelta

from django.conf import settings
from django.db.models import Exists, F, OuterRef, Q
from django.urls import reverse
from django.utils import timezone

from apps.cart.models import Cart


def carts_to_remind(now=None):
    """Carts idle for ABANDONED_CART_HOURS (but not older than ABANDONED_CART_MAX_AGE_HOURS), not yet reminded
    since they last changed, whose owner has a verified mobile and hasn't ordered since."""
    from apps.orders.models import Order

    now = now or timezone.now()
    ordered_since = Order.objects.filter(user=OuterRef("user"), created_at__gte=OuterRef("updated_at"))
    return (
        Cart.objects.filter(
            user__isnull=False, user__is_active=True, user__phone_verified=True, items__isnull=False,
            updated_at__lte=now - timedelta(hours=settings.ABANDONED_CART_HOURS),
            updated_at__gte=now - timedelta(hours=settings.ABANDONED_CART_MAX_AGE_HOURS),
        )
        .filter(Q(reminded_at__isnull=True) | Q(reminded_at__lt=F("updated_at")))
        .filter(~Exists(ordered_since))
        .select_related("user")
        .distinct()
    )


def remind_abandoned_carts(*, now=None) -> int:
    from apps.common import sms
    from apps.common.services import get_settings

    now = now or timezone.now()
    link = f"{settings.SITE_URL.rstrip('/')}{reverse('cart:detail')}"
    store = get_settings().store_name
    sent = 0
    for cart in carts_to_remind(now):
        if sms.notify(cart.user.phone, f"{store}: کالاهای سبد خریدتان هنوز منتظر شماست. تکمیل خرید: {link}"):
            Cart.objects.filter(pk=cart.pk).update(reminded_at=now)  # update() leaves updated_at alone
            sent += 1
    return sent
