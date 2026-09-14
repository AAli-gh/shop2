from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from apps.cart.models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ("product", "quantity")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "items_count", "updated_ago", "updated_at")
    inlines = [CartItemInline]

    @admin.display(description="مالک")
    def owner(self, obj):
        if obj.user:
            return format_html(
                '<a href="/admin/accounts/user/{}/change/">{}</a>', obj.user_id, obj.user
            )
        return f"مهمان (session {obj.session_key or '—'})"

    @admin.display(description="اقلام")
    def items_count(self, obj):
        return obj.items.count()

    @admin.display(description="آخرین تغییر")
    def updated_ago(self, obj):
        hours = (timezone.now() - obj.updated_at).total_seconds() / 3600
        if hours < 1:
            return "همین حالا"
        if hours < 24:
            return f"{int(hours)} ساعت پیش"
        return f"{int(hours / 24)} روز پیش"

    def get_queryset(self, request):
        # only carts that still hold items are interesting (abandoned carts)
        return Cart.objects.filter(items__isnull=False).distinct()

    def has_add_permission(self, request):
        return False
