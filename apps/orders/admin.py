import csv
from datetime import datetime

from django.contrib import admin, messages
from django.http import HttpResponse
from django.utils.html import format_html
from django.utils import timezone

from apps.orders.models import Order, OrderItem, ShippingAddress, ShippingMethod
from apps.orders.services import OrderError, needs_manual_refund, transition_status


@admin.register(ShippingMethod)
class ShippingMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "description", "sort_order", "is_active")
    list_editable = ("price", "sort_order", "is_active")
    search_fields = ("name",)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product", "product_name", "unit_price", "quantity", "line_total")

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ShippingAddressInline(admin.StackedInline):
    model = ShippingAddress
    extra = 0
    readonly_fields = ("full_name", "phone", "province", "city", "postal_code", "address_line")

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


STATUS_COLORS = {
    Order.Status.PENDING_PAYMENT: "#b45309",
    Order.Status.PAID: "#1d4ed8",
    Order.Status.PROCESSING: "#7c3aed",
    Order.Status.SHIPPED: "#0369a1",
    Order.Status.DELIVERED: "#15803d",
    Order.Status.CANCELLED: "#b91c1c",
}


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number", "user_link", "status_badge", "total",
        "coupon_code", "created_at",
    )
    list_filter = ("status",)
    search_fields = ("order_number", "user__email")
    date_hierarchy = "created_at"
    readonly_fields = (
        "order_number", "user", "items_subtotal", "discount_amount",
        "shipping_cost", "total", "coupon", "coupon_code", "payment_ref",
        "created_at", "updated_at",
    )
    inlines = [OrderItemInline, ShippingAddressInline]
    actions = ["mark_shipped", "mark_processing", "mark_delivered", "export_csv"]

    fieldsets = (
        ("وضعیت (طبق چرخه: پردازش ← پرداخت‌شده، ارسال ← پردازش، تحویل ← ارسال)", {"fields": ("status",)}),
        ("مشخصات سفارش", {"fields": ("order_number", "user", "payment_ref")}),
        ("ارسال بار", {"fields": ("tracking_code", "shipping_note"), "description": "کد رهگیری مرسوله — پس از ثبت، وضعیت را به «ارسال شد» تغییر دهید تا به مشتری ایمیل شود."}),
        ("مالی (فقط‌خواندنی)", {"fields": ("items_subtotal", "discount_amount", "shipping_cost", "total", "coupon", "coupon_code")}),
        ("تاریخ‌ها", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="مشتری")
    def user_link(self, obj):
        return format_html('<a href="/admin/accounts/user/{}/change/">{}</a>', obj.user_id, obj.user.email)

    @admin.display(description="وضعیت")
    def status_badge(self, obj):
        color = STATUS_COLORS.get(obj.status, "#374151")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;border-radius:9999px;font-size:11px">{}</span>',
            color, obj.get_status_display(),
        )

    def save_model(self, request, obj, form, change):
        # status changes must follow the transition map (emails + shop log included)
        if change and "status" in form.changed_data:
            old_status = Order.objects.get(pk=obj.pk).status
            # persist shipping fields first (transition_status only saves status)
            Order.objects.filter(pk=obj.pk).update(
                tracking_code=form.cleaned_data.get("tracking_code", ""),
                shipping_note=form.cleaned_data.get("shipping_note", ""),
            )
            obj.refresh_from_db()
            try:
                updated = transition_status(order=obj, new_status=form.cleaned_data["status"])
                obj.status = updated.status
                messages.success(
                    request,
                    f"وضعیت سفارش {obj.order_number} از «{Order.Status(old_status).label}» "
                    f"به «{updated.get_status_display()}» تغییر کرد.",
                )
                if updated.status == Order.Status.CANCELLED:
                    if updated.wallet_used:
                        messages.info(request, f"{updated.wallet_used:,} تومان به کیف پول مشتری برگشت داده شد.")
                    if needs_manual_refund(updated):
                        messages.warning(
                            request,
                            f"این سفارش آنلاین پرداخت شده بود؛ {updated.total - updated.wallet_used:,} تومان "
                            f"(کد پیگیری {updated.payment_ref}) را دستی به حساب مشتری بازگردانید.",
                        )
            except OrderError as exc:
                messages.error(request, f"تغییر وضعیت مجاز نیست: {exc}")
                obj.status = old_status
            return
        super().save_model(request, obj, form, change)

    @admin.action(description="✅ تأیید و ارسال مرسوله (shipped)")
    def mark_shipped(self, request, queryset):
        missing = queryset.filter(status=Order.Status.PROCESSING, tracking_code="").count()
        if missing:
            messages.warning(
                request,
                f"{missing} سفارش بدون کد رهگیری است — بعداً در صفحه سفارش واردش کنید.",
            )
        self._transition_many(request, queryset, Order.Status.SHIPPED)

    @admin.action(description="🔨 در حال پردازش (processing)")
    def mark_processing(self, request, queryset):
        self._transition_many(request, queryset, Order.Status.PROCESSING)

    @admin.action(description="📦 تحویل داده شد (delivered)")
    def mark_delivered(self, request, queryset):
        self._transition_many(request, queryset, Order.Status.DELIVERED)

    def _transition_many(self, request, queryset, new_status):
        ok, failed = 0, []
        for order in queryset:
            try:
                transition_status(order=order, new_status=new_status)
                ok += 1
            except OrderError as exc:
                failed.append(f"{order.order_number}: {exc}")
        if ok:
            messages.success(request, f"{ok} سفارش به «{Order.Status(new_status).label}» تغییر کرد.")
        for f in failed:
            messages.error(request, f)

    @admin.action(description="خروجی CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename=orders-{datetime.now():%Y%m%d}.csv'
        response.write("﻿")  # Excel UTF-8 BOM
        writer = csv.writer(response)
        writer.writerow(["شماره سفارش", "ایمیل", "وضعیت", "جمع کالا", "تخفیف", "ارسال", "جمع کل", "تاریخ"])
        for o in queryset.select_related("user"):
            writer.writerow([
                o.order_number, o.user.email, o.get_status_display(),
                o.items_subtotal, o.discount_amount, o.shipping_cost, o.total,
                timezone.localtime(o.created_at).strftime("%Y/%m/%d %H:%M"),
            ])
        return response
