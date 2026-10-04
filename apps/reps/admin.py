from datetime import timedelta

from django.contrib import admin
from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.common.admin_jalali import jalali_column
from apps.reps.models import RepCustomer, SalesRep


@admin.register(SalesRep)
class SalesRepAdmin(admin.ModelAdmin):
    """Make an account a sales rep: pick the user (who signed up on the site), give a code and region."""

    list_display = ("__str__", "region", "phone", "customer_count", "orders_30_days", "sales_30_days", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "user__name", "user__email", "user__phone", "region")
    autocomplete_fields = ("user",)
    readonly_fields = ("created_jalali",)
    created_jalali = jalali_column("created_at", "تاریخ ثبت")

    def get_queryset(self, request):
        since = timezone.now() - timedelta(days=30)
        recent = Q(orders__created_at__gte=since) & ~Q(orders__status="cancelled")
        return super().get_queryset(request).select_related("user").annotate(
            _customers=Count("customers", distinct=True),
            _orders=Count("orders", filter=recent, distinct=True),
            _sales=Sum("orders__total", filter=recent),
        )

    @admin.display(description="مشتری‌ها", ordering="_customers")
    def customer_count(self, obj):
        return obj._customers

    @admin.display(description="سفارش ۳۰ روز", ordering="_orders")
    def orders_30_days(self, obj):
        return obj._orders

    @admin.display(description="فروش ۳۰ روز (تومان)", ordering="_sales")
    def sales_30_days(self, obj):
        return f"{obj._sales or 0:,}"


@admin.register(RepCustomer)
class RepCustomerAdmin(admin.ModelAdmin):
    list_display = ("shop_name", "owner_name", "phone", "city", "rep", "is_active", "created_jalali")
    list_filter = ("is_active", ("rep", admin.RelatedOnlyFieldListFilter), "province")
    search_fields = ("shop_name", "owner_name", "phone", "city", "rep__code")
    autocomplete_fields = ("rep",)
    list_select_related = ("rep__user",)
    created_jalali = jalali_column("created_at", "تاریخ ثبت")
