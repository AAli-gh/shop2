from django.contrib import admin
from django.utils import timezone

from apps.blog.models import Post


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "is_published", "published_at", "created_at")
    list_filter = ("kind", "is_published")
    search_fields = ("title", "excerpt", "body")
    readonly_fields = ("published_at", "created_at")

    def save_model(self, request, obj, form, change):
        if obj.is_published and not obj.published_at:
            obj.published_at = timezone.now()
        super().save_model(request, obj, form, change)
