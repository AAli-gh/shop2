from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.core.exceptions import PermissionDenied

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

    # Staff with "change user" (e.g. the support role) look after customers. Without these limits
    # they could tick superuser on their own account, or reset a manager's password or phone and
    # sign in as them; only a superuser grants access or edits other staff.
    PRIVILEGE_FIELDS = ("is_staff", "is_superuser", "groups", "user_permissions")

    def get_readonly_fields(self, request, obj=None):
        fields = tuple(super().get_readonly_fields(request, obj))
        return fields if request.user.is_superuser else fields + self.PRIVILEGE_FIELDS

    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.is_staff and obj.pk != request.user.pk and not request.user.is_superuser:
            return False
        return super().has_change_permission(request, obj)

    def user_change_password(self, request, id, form_url=""):
        if not request.user.is_superuser:
            raise PermissionDenied
        return super().user_change_password(request, id, form_url)

    @admin.action(description="تأیید دستی ایمیل انتخاب‌شده‌ها")
    def verify_emails(self, request, queryset):
        if not request.user.is_superuser:
            queryset = queryset.filter(is_staff=False)
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
