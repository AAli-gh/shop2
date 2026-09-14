from django.core.cache import cache

from apps.common.models import SiteSettings


def get_settings() -> SiteSettings:
    settings = cache.get("site_settings")
    if settings is None:
        settings = SiteSettings.load()
        cache.set("site_settings", settings, 60)
    return settings
