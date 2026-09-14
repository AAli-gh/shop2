from django.contrib import admin
from django.utils import timezone

from apps.blog.models import Post
from apps.common.admin_jalali import jalali_column


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "is_published", "published_jalali", "created_jalali")
    list_filter = ("kind", "is_published")
    search_fields = ("title", "excerpt", "body")
    readonly_fields = ("published_jalali", "created_jalali")

    published_jalali = jalali_column("published_at", "تاریخ انتشار")
    created_jalali = jalali_column("created_at", "تاریخ ساخت")

    def save_model(self, request, obj, form, change):
        if obj.is_published and not obj.published_at:
            obj.published_at = timezone.now()
        super().save_model(request, obj, form, change)
