from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.accounts.models import Address, User
from apps.common.admin_jalali import jalali_column, jalali_date_filter


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["-date_joined"]
    list_display = ("__str__", "name", "phone", "phone_verified", "email_verified", "is_staff", "joined_jalali")
    search_fields = ("email", "name", "phone")
    list_filter = (
        "is_staff", "is_superuser", "is_active", "phone_verified", "email_verified",
        jalali_date_filter("date_joined", "تاریخ عضویت"),
    )
    readonly_fields = ("last_login_jalali", "joined_jalali")

    joined_jalali = jalali_column("date_joined", "تاریخ عضویت")
    last_login_jalali = jalali_column("last_login", "آخرین ورود")
    actions = ["verify_emails"]

    @admin.action(description="تأیید دستی ایمیل انتخاب‌شده‌ها")
    def verify_emails(self, request, queryset):
        updated = queryset.filter(email_verified=False).update(
            email_verified=True, is_active=True
        )
        self.message_user(request, f"{updated} حساب تأیید و فعال شد.")

    fieldsets = (
        (None, {"fields": ("email", "phone", "phone_verified", "password")}),
        ("اطلاعات شخصی", {"fields": ("name",)}),
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
        ("تاریخ‌ها", {"fields": ("last_login_jalali", "joined_jalali")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),
    )


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("user", "full_name", "city", "phone", "is_default")
    list_filter = ("is_default", "city")
    search_fields = ("user__email", "user__phone", "full_name", "phone")
