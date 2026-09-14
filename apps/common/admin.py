from django.contrib import admin
from django.utils.html import format_html

from apps.common.models import ContactMessage, SiteSettings, StaticPage

admin.site.site_header = format_html(
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
        ("ارسال", {"fields": ("shipping_flat_rate", "free_shipping_threshold")}),
        ("ارتباط با مشتری", {"fields": ("contact_phone", "about_text")}),
        ("نمادهای اعتماد", {"fields": ("trust_badges_html",)}),
    )

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "subject", "is_read", "created_at")
    list_filter = ("is_read",)
    search_fields = ("name", "email", "subject")
    readonly_fields = ("name", "email", "subject", "body", "created_at")
    list_editable = ("is_read",)
    actions = ["mark_unread"]

    @admin.action(description="علامت‌گذاری به‌عنوان خوانده‌نشده")
    def mark_unread(self, request, queryset):
        queryset.update(is_read=False)


@admin.register(StaticPage)
class StaticPageAdmin(admin.ModelAdmin):
    list_display = ("title", "key", "updated_at")
    search_fields = ("title", "body")
    readonly_fields = ("updated_at",)
