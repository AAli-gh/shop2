import csv
from datetime import datetime

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils import timezone

from apps.accounts.otp import normalize_phone
from apps.common.admin_jalali import jalali_column, jalali_date_filter
from apps.orders.models import (
    Order, OrderItem, OrderNote, ReturnRequest, ReturnRequestItem, ShippingAddress, ShippingMethod,
)
from apps.orders.returns import ReturnError, complete_return, set_return_status, suggested_refund
from apps.orders.services import OrderError, needs_manual_refund, transition_status

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


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


class OrderNoteInline(admin.TabularInline):
    """Staff-only notes; existing notes are kept as a read-only history."""

    model = OrderNote
    extra = 1
    fields = ("body", "author", "created_jalali")
    readonly_fields = ("author", "created_jalali")
    verbose_name = "یادداشت داخلی (مشتری نمی‌بیند)"
    verbose_name_plural = "یادداشت‌های داخلی (مشتری نمی‌بیند)"

    created_jalali = jalali_column("created_at", "زمان")

    def has_change_permission(self, request, obj=None):
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
        "order_number", "user_link", "customer_name", "status_badge", "total",
        "coupon_code", "created_jalali",
    )
    list_filter = ("status", jalali_date_filter("created_at", "تاریخ ثبت"))
    # order number, customer email/mobile/name, or the name/phone on the shipping address
    search_fields = (
        "order_number", "user__email", "user__phone", "user__name",
        "shipping_address__full_name", "shipping_address__phone",
    )
    search_help_text = "شماره سفارش، موبایل، نام یا ایمیل مشتری"
    readonly_fields = (
        "order_number", "user", "items_subtotal", "discount_amount",
        "shipping_cost", "total", "coupon", "coupon_code", "payment_ref",
        "created_jalali", "updated_jalali", "delivered_jalali", "invoice_link",
    )
    inlines = [OrderNoteInline, OrderItemInline, ShippingAddressInline]

    created_jalali = jalali_column("created_at", "تاریخ ثبت")
    updated_jalali = jalali_column("updated_at", "آخرین تغییر")
    delivered_jalali = jalali_column("delivered_at", "تاریخ تحویل")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "shipping_address")

    def get_search_results(self, request, queryset, search_term):
        # Persian/Arabic digits and +98 numbers still find the stored 09xxxxxxxxx mobile
        term = search_term.translate(_DIGITS).strip()
        return super().get_search_results(request, queryset, normalize_phone(term) or term)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, OrderNote) and instance.author_id is None:
                instance.author = request.user
            instance.save()
        for obj in formset.deleted_objects:
            obj.delete()
        formset.save_m2m()

    @admin.display(description="نام گیرنده")
    def customer_name(self, obj):
        address = getattr(obj, "shipping_address", None)
        return address.full_name if address else "—"
    actions = ["mark_shipped", "mark_processing", "mark_delivered", "export_csv"]

    fieldsets = (
        ("وضعیت (طبق چرخه: پردازش ← پرداخت‌شده، ارسال ← پردازش، تحویل ← ارسال)", {"fields": ("status",)}),
        ("مشخصات سفارش", {"fields": ("order_number", "user", "payment_ref", "invoice_link")}),
        ("ارسال بار", {"fields": ("tracking_code", "shipping_note"), "description": "کد رهگیری مرسوله — پس از ثبت، وضعیت را به «ارسال شد» تغییر دهید تا به مشتری ایمیل شود."}),
        ("مالی (فقط‌خواندنی)", {"fields": ("items_subtotal", "discount_amount", "shipping_cost", "total", "coupon", "coupon_code")}),
        ("تاریخ‌ها", {"fields": ("created_jalali", "updated_jalali", "delivered_jalali")}),
    )

    @admin.display(description="فاکتور")
    def invoice_link(self, obj):
        if not obj.pk:
            return "—"
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">مشاهده و چاپ فاکتور</a>',
            reverse("orders:invoice", args=[obj.order_number]),
        )

    @admin.display(description="مشتری")
    def user_link(self, obj):
        return format_html('<a href="/admin/accounts/user/{}/change/">{}</a>', obj.user_id, obj.user)

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
                o.order_number, o.user, o.get_status_display(),
                o.items_subtotal, o.discount_amount, o.shipping_cost, o.total,
                timezone.localtime(o.created_at).strftime("%Y/%m/%d %H:%M"),
            ])
        return response


class ReturnRequestItemInline(admin.TabularInline):
    model = ReturnRequestItem
    extra = 0
    readonly_fields = ("order_item", "quantity")

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = ("__str__", "order_link", "reason", "resolution", "status", "created_jalali")
    list_filter = ("status", "reason", "resolution", jalali_date_filter("created_at", "تاریخ ثبت"))
    search_fields = ("order__order_number", "order__user__email", "order__user__phone")
    readonly_fields = (
        "order_link", "reason", "resolution", "description", "photo", "completion",
        "created_jalali", "updated_jalali",
    )
    fieldsets = (
        ("بررسی (مسیر: در انتظار ← تأیید/رد، تأیید ← دریافت کالا/رد، دریافت کالا ← دکمه تکمیل)", {"fields": ("status", "staff_note", "completion")}),
        ("درخواست مشتری", {"fields": ("order_link", "reason", "resolution", "description", "photo")}),
        ("تاریخ‌ها", {"fields": ("created_jalali", "updated_jalali")}),
    )
    inlines = [ReturnRequestItemInline]

    created_jalali = jalali_column("created_at", "تاریخ ثبت")
    updated_jalali = jalali_column("updated_at", "آخرین تغییر")

    def has_add_permission(self, request):
        return False

    def get_urls(self):
        custom = [
            path("<int:pk>/complete/", self.admin_site.admin_view(self.complete_view), name="orders_returnrequest_complete"),
        ]
        return custom + super().get_urls()

    @admin.display(description="تکمیل")
    def completion(self, obj):
        if obj.status == ReturnRequest.Status.RECEIVED:
            return format_html(
                '<a class="button" href="{}">تکمیل مرجوعی (بازگشت وجه و موجودی)</a>',
                reverse("admin:orders_returnrequest_complete", args=[obj.pk]),
            )
        if obj.status == ReturnRequest.Status.COMPLETED:
            refund = f"{obj.refund_amount:,} تومان به کیف پول" if obj.refund_amount else "بدون بازگشت به کیف پول"
            stock = "کالا به انبار برگشت" if obj.restocked else "بدون برگشت به انبار"
            return f"{refund} · {stock}"
        return "پس از «کالا دریافت شد» فعال می‌شود."

    def complete_view(self, request, pk):
        return_request = get_object_or_404(ReturnRequest.objects.select_related("order__user"), pk=pk)
        if not self.has_change_permission(request, return_request):
            raise PermissionDenied
        change_url = reverse("admin:orders_returnrequest_change", args=[pk])
        if return_request.status != ReturnRequest.Status.RECEIVED:
            messages.error(request, "فقط درخواستی که کالای آن به فروشگاه رسیده قابل تکمیل است.")
            return redirect(change_url)

        if request.method == "POST":
            try:
                completed = complete_return(
                    return_request=return_request,
                    refund_to_wallet=request.POST.get("refund_to_wallet") == "on",
                    restock=request.POST.get("restock") == "on",
                    staff_note=request.POST.get("staff_note", "").strip() or None,
                )
            except ReturnError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f"مرجوعی تکمیل شد: {self.completion(completed)}. به مشتری اطلاع داده شد.")
                return redirect(change_url)

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "original": return_request,
            "title": f"تکمیل {return_request}",
            "items": return_request.items.select_related("order_item"),
            "suggested_refund": suggested_refund(return_request),
            "refund_default": return_request.resolution == ReturnRequest.Resolution.REFUND,
            "change_url": change_url,
        }
        return render(request, "admin/orders/returnrequest/complete.html", context)

    @admin.display(description="سفارش")
    def order_link(self, obj):
        return format_html(
            '<a href="{}">{}</a>', reverse("admin:orders_order_change", args=[obj.order_id]), obj.order.order_number,
        )

    @admin.display(description="عکس")
    def photo(self, obj):
        if not obj.image:
            return "—"
        return format_html('<a href="{0}" target="_blank"><img src="{0}" style="max-height:160px;border-radius:8px"></a>', obj.image.url)

    def save_model(self, request, obj, form, change):
        # status changes go through the workflow so the customer is notified
        if change and "status" in form.changed_data:
            try:
                set_return_status(
                    return_request=obj, status=form.cleaned_data["status"],
                    staff_note=form.cleaned_data.get("staff_note", ""),
                )
                messages.success(request, f"وضعیت به «{obj.get_status_display()}» تغییر کرد و به مشتری اطلاع داده شد.")
            except ReturnError as exc:
                messages.error(request, str(exc))
            return
        super().save_model(request, obj, form, change)
