from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from apps.discounts.models import Coupon


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = (
        "code", "kind", "value", "min_order_amount",
        "valid_to", "usage_display", "health", "is_active",
    )
    list_filter = ("kind", "is_active")
    search_fields = ("code",)
    readonly_fields = ("used_count",)

    @admin.display(description="ظرفیت")
    def usage_display(self, obj):
        limit = obj.usage_limit if obj.usage_limit is not None else "∞"
        return f"{obj.used_count} / {limit}"

    @admin.display(description="وضعیت")
    def health(self, obj):
        now = timezone.now()
        if not obj.is_active:
            color, label = "#6b7280", "غیرفعال"
        elif obj.valid_from and now < obj.valid_from:
            color, label = "#a16207", "هنوز شروع نشده"
        elif obj.valid_to and now > obj.valid_to:
            color, label = "#b91c1c", "منقضی"
        elif obj.usage_limit is not None and obj.used_count >= obj.usage_limit:
            color, label = "#b91c1c", "ظرفیت پر"
        else:
            color, label = "#15803d", "سالم"
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;border-radius:9999px;font-size:11px">{}</span>',
            color, label,
        )
