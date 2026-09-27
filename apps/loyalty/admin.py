from django.contrib import admin
from django.db import transaction
from django.db.models import Count

from apps.common.admin_jalali import jalali_column, jalali_date_filter
from apps.loyalty.models import LoyaltyAccount, PointTransaction


class PointTransactionInline(admin.TabularInline):
    model = PointTransaction
    fields = ("kind", "points", "order", "note", "created_jalali")
    readonly_fields = fields
    extra = 0
    can_delete = False
    ordering = ("-created_at",)
    created_jalali = jalali_column("created_at", "تاریخ")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(LoyaltyAccount)
class LoyaltyAccountAdmin(admin.ModelAdmin):
    list_display = ("user", "points", "referral_code", "referred_by", "referral_count", "referral_rewarded", "created_jalali")
    list_filter = ("referral_rewarded", jalali_date_filter("created_at", "تاریخ عضویت"))
    search_fields = ("user__email", "user__phone", "user__name", "referral_code")
    # the balance only moves through point transactions, so it always matches the history
    readonly_fields = ("user", "points", "referral_code", "referred_by", "referral_rewarded", "created_jalali")
    inlines = [PointTransactionInline]
    created_jalali = jalali_column("created_at", "تاریخ عضویت")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "referred_by").annotate(
            _referrals=Count("user__referrals", distinct=True),
        )

    @admin.display(description="معرفی‌ها", ordering="_referrals")
    def referral_count(self, obj):
        return obj._referrals

    def has_add_permission(self, request):
        return False


@admin.register(PointTransaction)
class PointTransactionAdmin(admin.ModelAdmin):
    """History of every point movement; staff add manual corrections here (kind is always «manual»)."""

    list_display = ("account", "kind", "points", "order", "note", "created_jalali")
    list_filter = ("kind", jalali_date_filter("created_at", "تاریخ"))
    search_fields = ("account__user__email", "account__user__phone", "account__referral_code", "order__order_number")
    autocomplete_fields = ("account",)
    created_jalali = jalali_column("created_at", "تاریخ")

    def get_fields(self, request, obj=None):
        return ("account", "points", "note") if obj is None else ("account", "kind", "points", "order", "note", "created_jalali")

    def get_readonly_fields(self, request, obj=None):
        return () if obj is None else self.get_fields(request, obj)

    def save_model(self, request, obj, form, change):
        if change:
            return
        from apps.loyalty.services import _add

        with transaction.atomic():
            saved = _add(obj.account, PointTransaction.Kind.ADJUST, obj.points,
                         note=(obj.note or f"اصلاح دستی توسط {request.user}")[:200])
        obj.pk = saved.pk

    def has_change_permission(self, request, obj=None):
        return obj is None and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False
