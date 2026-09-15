from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from apps.common.lastvisited import LAST_VISITED_LIMIT  # noqa: F401  (keep module import light)


def _send(user_email: str, subject: str, template: str, context: dict) -> None:
    if not user_email:
        return  # phone-login accounts have no email; they get the SMS instead
    body = render_to_string(template, context)
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user_email], fail_silently=True)


def _admin_link(url_name: str, pk) -> str:
    from django.urls import reverse

    return settings.SITE_URL.rstrip("/") + reverse(url_name, args=[pk])


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
        f"بررسی: {_admin_link('admin:orders_returnrequest_change', return_request.pk)}",
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
    text = f"درخواست مرجوعی سفارش {order.order_number}: {return_request.get_status_display()}"
    if return_request.refund_amount:
        text += f". {return_request.refund_amount:,} تومان به کیف پول شما برگشت داده شد."
    _sms(order, text)


def order_paid_staff(order) -> None:
    """Tell the shop managers a paid order is waiting to be prepared (SMS and email)."""
    text = f"سفارش جدید {order.order_number}: {order.total:,} تومان، {order.items.count()} قلم"
    _notify_staff(
        text,
        f"سفارش جدید پرداخت‌شده — {order.order_number}",
        f"{text}\nمشتری: {order.user}\nمشاهده: {_admin_link('admin:orders_order_change', order.pk)}",
    )


def low_stock_staff(rows) -> None:
    """Tell the managers which products just fell to the low-stock threshold; rows are (name, units left)."""
    text = "کمبود موجودی: " + "، ".join(f"{name} ({left} عدد)" for name, left in rows)
    _notify_staff(text, "هشدار کمبود موجودی", text)


def _notify_staff(text: str, subject: str, body: str) -> None:
    """SMS to ORDER_NOTIFY_PHONES and email to ORDER_NOTIFY_EMAILS (or ADMINS); failures never propagate."""
    from apps.common import sms
    from apps.common.services import get_settings

    store = get_settings().store_name
    for phone in settings.ORDER_NOTIFY_PHONES:
        sms.notify(phone, f"{store}: {text}")
    recipients = settings.ORDER_NOTIFY_EMAILS or [email for _, email in settings.ADMINS]
    if recipients:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=True)


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
