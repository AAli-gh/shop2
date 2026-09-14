from django.urls import path, re_path

from apps.catalog import views

app_name = "catalog"

# Unicode-aware slugs (Persian category/product names)
UNICODE_SLUG = r"[\w\-]+"

urlpatterns = [
    path("", views.home, name="home"),
    path("products/", views.product_list, name="product_list"),
    path("search/live/", views.live_search, name="live_search"),
    path("compare/", views.compare_page, name="compare"),
    path("compare/toggle/<path:slug>/", views.compare_toggle, name="compare_toggle"),
    path("compare/remove/<path:slug>/", views.compare_remove, name="compare_remove"),
    re_path(rf"^c/(?P<category_slug>{UNICODE_SLUG})/$", views.product_list, name="category"),
    re_path(rf"^brand/(?P<brand_slug>{UNICODE_SLUG})/$", views.brand_page, name="brand"),
    re_path(rf"^product/(?P<slug>{UNICODE_SLUG})/$", views.product_detail, name="detail"),
    re_path(rf"^product/(?P<slug>{UNICODE_SLUG})/restock/$", views.restock_notify, name="restock_notify"),
]
