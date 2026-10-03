from django.contrib import admin

from apps.common.admin_jalali import jalali_column, jalali_date_filter
from apps.crm.models import WinBackMessage


@admin.register(WinBackMessage)
class WinBackMessageAdmin(admin.ModelAdmin):
    """Offers the win-back campaign sent; the report at /dashboard/customers/ shows how they did."""

    list_display = ("user", "channel", "coupon", "last_purchase_jalali", "sent_jalali")
    list_filter = ("channel", jalali_date_filter("sent_at", "تاریخ ارسال"))
    search_fields = ("user__email", "user__phone", "user__name", "coupon__code")
    readonly_fields = ("user", "coupon", "channel", "last_purchase_jalali", "sent_jalali")
    exclude = ("last_purchase_at",)

    sent_jalali = jalali_column("sent_at", "زمان ارسال")
    last_purchase_jalali = jalali_column("last_purchase_at", "آخرین خرید")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
