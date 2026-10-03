from django.contrib import admin
from django.utils.safestring import mark_safe

from apps.common.admin_jalali import jalali_column, jalali_date_filter
from apps.common.models import ContactMessage, SiteSettings, StaticPage

# static markup with no interpolated values
admin.site.site_header = mark_safe(
    'مدیریت فروشگاه <a href="/dashboard/" style="font-size:0.6em;font-weight:normal;'
    'color:#a5d1e1;margin-inline-start:1rem;text-decoration:none">→ داشبورد آمار</a>'
)
admin.site.site_title = "مدیریت فروشگاه"
admin.site.index_title = "پیشخوان مدیریت"


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ("store_name", "shipping_flat_rate", "free_shipping_threshold")
    fieldsets = (
        (None, {"fields": ("store_name",)}),
        ("ارسال و نصب", {"fields": ("shipping_flat_rate", "free_shipping_threshold", "install_fee")}),
        ("باشگاه مشتریان و معرفی دوستان", {"fields": (
            "loyalty_enabled", "loyalty_toman_per_point", "loyalty_point_value", "loyalty_min_redeem_points",
            "referral_referrer_points", "referral_friend_points", "referral_min_order_amount",
        )}),
        ("پیش‌بینی موجودی", {"fields": ("restock_lead_days",)}),
        ("بازگرداندن مشتریان خوابیده", {"fields": (
            "winback_enabled", "winback_after_days", "winback_percent", "winback_max_discount", "winback_valid_days",
        )}),
        ("ارتباط با مشتری", {"fields": ("contact_phone", "about_text")}),
        ("اطلاعات فروشنده (روی فاکتور)", {"fields": ("legal_name", "national_id", "economic_code", "address", "postal_code")}),
        ("نمادهای اعتماد", {"fields": ("trust_badges_html",)}),
        ("آمار بازدید", {"fields": ("ga_measurement_id", "analytics_head_html"), "classes": ("collapse",)}),
        ("گفتگو با مشتری", {"fields": ("whatsapp_number", "telegram_username", "chat_widget_html"), "classes": ("collapse",)}),
    )

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "subject", "is_read", "created_jalali")
    list_filter = ("is_read", jalali_date_filter("created_at", "تاریخ"))
    search_fields = ("name", "email", "subject")
    readonly_fields = ("name", "email", "subject", "body", "created_jalali")

    created_jalali = jalali_column("created_at", "تاریخ")
    list_editable = ("is_read",)
    actions = ["mark_unread"]

    @admin.action(description="علامت‌گذاری به‌عنوان خوانده‌نشده")
    def mark_unread(self, request, queryset):
        queryset.update(is_read=False)


@admin.register(StaticPage)
class StaticPageAdmin(admin.ModelAdmin):
    list_display = ("title", "key", "updated_jalali")
    search_fields = ("title", "body")
    readonly_fields = ("updated_jalali",)

    updated_jalali = jalali_column("updated_at", "آخرین ویرایش")
