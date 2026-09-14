from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.accounts.models import Address, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["-date_joined"]
    list_display = ("email", "name", "phone", "email_verified", "is_staff", "date_joined")
    search_fields = ("email", "name", "phone")
    list_filter = ("is_staff", "is_superuser", "is_active", "email_verified")
    actions = ["verify_emails"]

    @admin.action(description="تأیید دستی ایمیل انتخاب‌شده‌ها")
    def verify_emails(self, request, queryset):
        updated = queryset.filter(email_verified=False).update(
            email_verified=True, is_active=True
        )
        self.message_user(request, f"{updated} حساب تأیید و فعال شد.")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("اطلاعات شخصی", {"fields": ("name", "phone")}),
        (
            "دسترسی‌ها",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        ("تاریخ‌ها", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),
    )


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("user", "full_name", "city", "phone", "is_default")
    list_filter = ("is_default", "city")
    search_fields = ("user__email", "full_name", "phone")
