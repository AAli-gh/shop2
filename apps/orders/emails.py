from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from apps.common.lastvisited import LAST_VISITED_LIMIT  # noqa: F401  (keep module import light)


def _send(user_email: str, subject: str, template: str, context: dict) -> None:
    if not user_email:
        return  # phone-login accounts have no email; they get the SMS instead
    body = render_to_string(template, context)
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user_email], fail_silently=True)


def _sms(order, text: str) -> None:
    user = order.user
    if user.phone and user.phone_verified:
        from apps.common import sms
        from apps.common.services import get_settings

        sms.notify(user.phone, f"{get_settings().store_name}: {text}")


def order_placed(order) -> None:
    _send(
        order.user.email,
        f"سفارش شما ثبت شد — {order.order_number}",
        "orders/emails/order_placed.txt",
        {"order": order},
    )
    _sms(order, f"سفارش {order.order_number} ثبت شد. مبلغ: {order.total:,} تومان")


def order_status_changed(order) -> None:
    _send(
        order.user.email,
        f"وضعیت سفارش {order.order_number} تغییر کرد",
        "orders/emails/order_status.txt",
        {"order": order},
    )
    _sms(order, f"وضعیت سفارش {order.order_number}: {order.get_status_display()}")


def return_requested(return_request) -> None:
    """Tell the shop team (settings.ADMINS) that a return request is waiting for review."""
    from django.core.mail import mail_admins

    order = return_request.order
    lines = "\n".join(f"- {item.order_item.product_name} × {item.quantity}" for item in return_request.items.all())
    mail_admins(
        f"درخواست مرجوعی جدید — سفارش {order.order_number}",
        f"دلیل: {return_request.get_reason_display()}\n"
        f"درخواست مشتری: {return_request.get_resolution_display()}\n{lines}\n\n"
        f"{return_request.description}\n\n"
        f"بررسی: {settings.SITE_URL.rstrip('/')}/admin/orders/returnrequest/{return_request.pk}/change/",
        fail_silently=True,
    )


def return_status_changed(return_request) -> None:
    order = return_request.order
    _send(
        order.user.email,
        f"درخواست مرجوعی سفارش {order.order_number}",
        "orders/emails/return_status.txt",
        {"return_request": return_request, "order": order, "site_url": settings.SITE_URL.rstrip("/")},
    )
    _sms(order, f"درخواست مرجوعی سفارش {order.order_number}: {return_request.get_status_display()}")


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
