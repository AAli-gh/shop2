from django.contrib import admin

from apps.common.admin_jalali import jalali_column, jalali_date_filter
from apps.reviews.models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "user", "rating", "is_approved", "created_jalali")
    list_filter = ("is_approved", "rating", jalali_date_filter("created_at", "تاریخ ثبت"))

    created_jalali = jalali_column("created_at", "تاریخ ثبت")
    search_fields = ("product__name", "user__email", "body")
    list_editable = ("is_approved",)
    actions = ["approve_selected"]

    @admin.action(description="تأیید نظرات انتخاب‌شده")
    def approve_selected(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(request, f"{updated} نظر تأیید شد.")
