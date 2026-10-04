"""Telling the company about orders its sales reps place."""
from django.conf import settings
from django.urls import reverse


def rep_order_placed(order) -> None:
    """Email (ADMINS / ORDER_NOTIFY_EMAILS) and SMS (ORDER_NOTIFY_PHONES) that a rep's order awaits approval."""
    from apps.orders.emails import _staff_email, _staff_sms

    rep, shop = order.sales_rep, order.rep_customer
    link = settings.SITE_URL.rstrip("/") + reverse("admin:orders_order_change", args=[order.pk])
    lines = "\n".join(f"- {item.product_name} × {item.quantity}" for item in order.items.all())
    _staff_email(
        f"سفارش ویزیتور در انتظار تأیید — {order.order_number}",
        f"ویزیتور: {rep}\nمشتری: {shop} — {shop.phone}\nنحوه پرداخت: {order.get_payment_terms_display()}\n"
        f"مبلغ: {order.total:,} تومان\n\n{lines}\n\n"
        f"{('توضیح: ' + order.shipping_note) if order.shipping_note else ''}\n\nتأیید در پنل مدیریت: {link}",
    )
    _staff_sms(
        f"سفارش ویزیتور {order.order_number} به مبلغ {order.total:,} تومان منتظر تأیید است",
        event="order_paid_staff", params={"ORDER": order.order_number, "AMOUNT": f"{order.total:,}"},
    )
