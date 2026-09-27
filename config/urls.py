from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.generic import TemplateView

from apps.catalog.sitemaps import CategorySitemap, PostSitemap, ProductSitemap, StaticViewSitemap

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("cart/", include("apps.cart.urls")),
    path("reviews/", include("apps.reviews.urls")),
    path("wishlist/", include("apps.wishlist.urls")),
    path("wallet/", include("apps.wallet.urls")),
    path("club/", include("apps.loyalty.urls")),
    path("newsletter/", include("apps.newsletter.urls")),
    path("blog/", include("apps.blog.urls")),
    path("payments/", include("apps.payments.urls")),
    path("sitemap.xml", sitemap, {"sitemaps": {
        "products": ProductSitemap,
        "categories": CategorySitemap,
        "posts": PostSitemap,
        "static": StaticViewSitemap,
    }}, name="django.contrib.sitemaps.views.sitemap"),
    path("robots.txt", TemplateView.as_view(template_name="robots.txt", content_type="text/plain")),
    path("", include("apps.common.urls")),
    path("", include("apps.orders.urls")),
    path("api/v1/", include("apps.catalog.api_urls")),
    path("", include("apps.catalog.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
