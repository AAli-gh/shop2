from django.contrib import admin

from apps.wallet.models import GiftCard, GiftCardRedemption, Wallet, WalletTransaction


@admin.register(GiftCard)
class GiftCardAdmin(admin.ModelAdmin):
    list_display = ("code", "amount", "spent_amount", "remaining", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("code",)
    readonly_fields = ("spent_amount", "created_at")
    actions = ["deactivate"]

    @admin.action(description="غیرفعال‌سازی کدهای انتخابی")
    def deactivate(self, request, queryset):
        queryset.update(is_active=False)


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("user", "balance")
    search_fields = ("user__email",)


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ("wallet", "kind", "amount", "order", "gift_card", "created_at")
    list_filter = ("kind",)
    readonly_fields = ("wallet", "kind", "amount", "order", "gift_card", "created_at")

    def has_add_permission(self, request):
        return False


@admin.register(GiftCardRedemption)
class GiftCardRedemptionAdmin(admin.ModelAdmin):
    list_display = ("gift_card", "user", "amount", "created_at")
    search_fields = ("user__email", "gift_card__code")
    readonly_fields = ("gift_card", "user", "amount", "created_at")

    def has_add_permission(self, request):
        return False
