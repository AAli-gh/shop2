"""Ask the customer for a review a few days after their order arrived.

One message per order (SMS to a verified mobile, otherwise email), about the first product
they haven't reviewed yet; orders whose products are all reviewed are quietly marked as asked.
"""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.orders.models import Order


def orders_to_ask(now=None):
    now = now or timezone.now()
    return (
        Order.objects.filter(
            status=Order.Status.DELIVERED,
            sales_rep__isnull=True,  # a rep's order went to a shop, not to the account holder
            review_requested_at__isnull=True,
            delivered_at__lte=now - timedelta(days=settings.REVIEW_REQUEST_DAYS),
            delivered_at__gte=now - timedelta(days=settings.REVIEW_REQUEST_MAX_DAYS),
        )
        .select_related("user")
        .prefetch_related("items__product")
    )


def _unreviewed_product(order):
    """The first product of the order the customer hasn't reviewed yet, or None."""
    from apps.reviews.models import Review

    product_ids = [item.product_id for item in order.items.all() if item.product_id]
    reviewed = set(
        Review.objects.filter(user=order.user, product_id__in=product_ids).values_list("product_id", flat=True)
    )
    for item in order.items.all():
        if item.product_id and item.product_id not in reviewed and item.product.is_active:
            return item.product
    return None


def request_reviews(*, now=None) -> int:
    from django.core.mail import send_mail

    from apps.common import sms
    from apps.common.services import get_settings

    now = now or timezone.now()
    store = get_settings().store_name
    sent = 0
    for order in orders_to_ask(now):
        product = _unreviewed_product(order)
        if product is None:  # nothing left to ask about
            Order.objects.filter(pk=order.pk).update(review_requested_at=now)
            continue
        url = f"{settings.SITE_URL.rstrip('/')}{product.get_absolute_url()}#reviews-section"
        text = f"{store}: از «{product.name}» راضی بودید؟ نظر شما به بقیه کمک می‌کند: {url}"
        user = order.user
        if user.phone and user.phone_verified:
            delivered = sms.notify(user.phone, text, event="review_request", params={"PRODUCT": product.name})
        elif user.email:
            send_mail(f"نظر شما درباره {product.name}", text, settings.DEFAULT_FROM_EMAIL, [user.email],
                      fail_silently=True)
            delivered = True
        else:
            delivered = False
        if delivered:  # a failed SMS is retried on the next run
            Order.objects.filter(pk=order.pk).update(review_requested_at=now)
            sent += 1
    return sent
