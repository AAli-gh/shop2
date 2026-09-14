from django.contrib import admin

from apps.common.admin_jalali import jalali_column, jalali_date_filter
from apps.wallet.models import GiftCard, GiftCardRedemption, Wallet, WalletTransaction


@admin.register(GiftCard)
class GiftCardAdmin(admin.ModelAdmin):
    list_display = ("code", "amount", "spent_amount", "remaining", "is_active", "created_jalali")
    list_filter = ("is_active",)
    search_fields = ("code",)
    readonly_fields = ("spent_amount", "created_jalali")
    actions = ["deactivate"]

    created_jalali = jalali_column("created_at", "تاریخ ساخت")

    @admin.action(description="غیرفعال‌سازی کدهای انتخابی")
    def deactivate(self, request, queryset):
        queryset.update(is_active=False)


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("user", "balance")
    search_fields = ("user__email",)


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ("wallet", "kind", "amount", "order", "gift_card", "created_jalali")
    list_filter = ("kind", jalali_date_filter("created_at", "تاریخ"))
    readonly_fields = ("wallet", "kind", "amount", "order", "gift_card", "created_jalali")
    exclude = ("created_at",)

    created_jalali = jalali_column("created_at", "تاریخ")

    def has_add_permission(self, request):
        return False


@admin.register(GiftCardRedemption)
class GiftCardRedemptionAdmin(admin.ModelAdmin):
    list_display = ("gift_card", "user", "amount", "created_jalali")
    search_fields = ("user__email", "user__phone", "gift_card__code")
    readonly_fields = ("gift_card", "user", "amount", "created_jalali")

    created_jalali = jalali_column("created_at", "تاریخ")

    def has_add_permission(self, request):
        return False
