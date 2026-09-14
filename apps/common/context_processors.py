from apps.catalog.models import Category
from apps.common.services import get_settings


def site_settings(request):
    settings_obj = get_settings()
    compare_count = len(request.session.get("compare", [])) if hasattr(request, "session") else 0
    return {
        "site_settings": settings_obj,
        "default_seo_description": f"{settings_obj.store_name} — خرید آنلاین با ارسال سریع و پرداخت امن",
        "compare_count": compare_count,
        "nav_categories": Category.objects.filter(is_active=True, parent__isnull=True).order_by("name")[:8],
    }
