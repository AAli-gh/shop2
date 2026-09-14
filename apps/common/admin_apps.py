from django.contrib.admin.apps import AdminConfig


class ShopAdminConfig(AdminConfig):
    """django.contrib.admin, with admin.site being the shop's site (password + SMS code sign-in)."""

    default_site = "apps.accounts.admin_site.ShopAdminSite"
