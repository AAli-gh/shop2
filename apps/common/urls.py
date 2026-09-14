from django.urls import path

from apps.common import views, views_staff

app_name = "common"

urlpatterns = [
    path("about/", views.about, name="about"),
    path("faq/", views.static_page, {"key": "faq"}, name="faq"),
    path("return-policy/", views.static_page, {"key": "return_policy"}, name="return_policy"),
    path("terms/", views.static_page, {"key": "terms"}, name="terms"),
    path("privacy/", views.static_page, {"key": "privacy"}, name="privacy"),
    path("contact/", views.contact, name="contact"),
    path("dashboard/", views_staff.dashboard, name="dashboard"),
    path("logs/", views_staff.logs_view, name="logs"),
    path("logs/download/", views_staff.logs_download, name="logs_download"),
    path("import-products/", views_staff.import_products, name="import_products"),
]
