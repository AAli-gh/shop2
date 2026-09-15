"""Price-drop alerts: a signed-in customer follows a product and hears once when its price falls."""
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from apps.catalog.models import PriceAlert


def is_following(user, product) -> bool:
    if not user.is_authenticated:
        return False
    return PriceAlert.objects.filter(user=user, product=product, notified_at__isnull=True).exists()


def toggle(*, user, product) -> bool:
    """Follow or stop following; following again starts from today's price. Returns whether it is followed now."""
    if is_following(user, product):
        PriceAlert.objects.filter(user=user, product=product).delete()
        return False
    PriceAlert.objects.update_or_create(
        user=user, product=product, defaults={"price_at_signup": product.effective_price, "notified_at": None},
    )
    return True


def send_price_alerts(*, now=None) -> int:
    """Notify followers of products now cheaper than when they subscribed (SMS, or email without a mobile)."""
    from apps.common import sms
    from apps.common.services import get_settings

    now = now or timezone.now()
    store = get_settings().store_name
    sent = 0
    alerts = PriceAlert.objects.filter(
        notified_at__isnull=True, product__is_active=True, user__is_active=True,
    ).select_related("product", "user")
    for alert in alerts:
        product, user = alert.product, alert.user
        price = product.effective_price
        if price >= alert.price_at_signup or not product.in_stock:
            continue
        url = f"{settings.SITE_URL.rstrip('/')}{product.get_absolute_url()}"
        text = f"قیمت «{product.name}» از {alert.price_at_signup:,} به {price:,} تومان کاهش یافت. {url}"
        if user.phone and user.phone_verified:
            delivered = sms.notify(user.phone, f"{store}: {text}")
        elif user.email:
            send_mail(f"کاهش قیمت: {product.name}", text, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)
            delivered = True
        else:
            delivered = False
        if delivered:  # a failed SMS is retried on the next run
            PriceAlert.objects.filter(pk=alert.pk).update(notified_at=now)
            sent += 1
    return sent
