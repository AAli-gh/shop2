from django.urls import path, re_path

from apps.catalog.urls import UNICODE_SLUG
from apps.guides import views

app_name = "guides"

urlpatterns = [
    path("", views.guide_list, name="list"),
    re_path(rf"^(?P<category_slug>{UNICODE_SLUG})/$", views.guide_detail, name="detail"),
]
