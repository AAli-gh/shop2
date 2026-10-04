"""Counters of work waiting for staff, shown on the admin home page."""
from datetime import datetime, time

from django import template
from django.urls import reverse
from django.utils import timezone

register = template.Library()


@register.simple_tag(takes_context=True)
def admin_pending_items(context):
    """Only items the signed-in staff member is allowed to view; each links to the filtered list."""
    from apps.catalog.forecast import at_risk_count
    from apps.catalog.models import Product
    from apps.catalog.search_report import missed_count
    from apps.common.models import ContactMessage
    from apps.orders.models import Order, ReturnRequest
    from apps.reviews.models import ProductQuestion, Review

    request = context.get("request")
    user = getattr(request, "user", None)
    if user is None or not user.is_staff:
        return []

    today_start = timezone.make_aware(datetime.combine(timezone.localdate(), time.min))
    candidates = [
        ("orders.view_order", "سفارش‌های امروز",
         lambda: Order.objects.filter(created_at__gte=today_start).exclude(status=Order.Status.CANCELLED).count(),
         reverse("admin:orders_order_changelist") + "?created_at_jalali=today"),
        ("orders.view_order", "سفارش ویزیتور منتظر تأیید",
         lambda: Order.objects.filter(status=Order.Status.AWAITING_APPROVAL).count(),
         reverse("admin:orders_order_changelist") + "?status__exact=approval"),
        ("orders.view_order", "آماده پردازش",
         lambda: Order.objects.filter(status=Order.Status.PAID).count(),
         reverse("admin:orders_order_changelist") + "?status__exact=paid"),
        ("orders.view_returnrequest", "مرجوعی در انتظار بررسی",
         lambda: ReturnRequest.objects.filter(status=ReturnRequest.Status.PENDING).count(),
         reverse("admin:orders_returnrequest_changelist") + "?status__exact=pending"),
        ("orders.view_returnrequest", "کالای مرجوعی رسیده",
         lambda: ReturnRequest.objects.filter(status=ReturnRequest.Status.RECEIVED).count(),
         reverse("admin:orders_returnrequest_changelist") + "?status__exact=received"),
        ("reviews.view_review", "نظر در انتظار تأیید",
         lambda: Review.objects.filter(is_approved=False).count(),
         reverse("admin:reviews_review_changelist") + "?is_approved__exact=0"),
        ("reviews.view_productquestion", "پرسش بی‌پاسخ",
         lambda: ProductQuestion.objects.filter(answer="").count(),
         reverse("admin:reviews_productquestion_changelist") + "?answered=no"),
        ("common.view_contactmessage", "پیام خوانده‌نشده",
         lambda: ContactMessage.objects.filter(is_read=False).count(),
         reverse("admin:common_contactmessage_changelist") + "?is_read__exact=0"),
        ("catalog.view_product", "محصول فعالِ ناموجود",
         lambda: Product.objects.filter(is_active=True, stock=0).count(),
         reverse("admin:catalog_product_changelist") + "?is_active__exact=1"),
        ("catalog.view_product", "رو به اتمام (پیش‌بینی)",
         lambda: at_risk_count(),
         reverse("common:stock_forecast")),
        ("catalog.view_searchterm", "جستجوی بی‌نتیجه",
         lambda: missed_count(),
         reverse("common:missed_searches")),
    ]
    return [
        {"label": label, "count": count(), "url": url}
        for perm, label, count, url in candidates
        if user.has_perm(perm)
    ]
