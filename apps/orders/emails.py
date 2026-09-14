from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from apps.common.lastvisited import LAST_VISITED_LIMIT  # noqa: F401  (keep module import light)


def _send(user_email: str, subject: str, template: str, context: dict) -> None:
    body = render_to_string(template, context)
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user_email], fail_silently=True)


def order_placed(order) -> None:
    _send(
        order.user.email,
        f"سفارش شما ثبت شد — {order.order_number}",
        "orders/emails/order_placed.txt",
        {"order": order},
    )


def order_status_changed(order) -> None:
    _send(
        order.user.email,
        f"وضعیت سفارش {order.order_number} تغییر کرد",
        "orders/emails/order_status.txt",
        {"order": order},
    )


def restock_available(product) -> int:
    """Notify pending restock subscribers; returns count sent."""
    from apps.catalog.models import RestockNotification

    pending = RestockNotification.objects.filter(product=product, notified=False)
    sent = 0
    for req in pending:
        try:
            _send(
                req.email,
                f"موجود شد: {product.name}",
                "catalog/emails/restock_available.txt",
                {"product": product},
            )
            sent += 1
        except Exception:
            continue
    pending.update(notified=True)
    return sent
