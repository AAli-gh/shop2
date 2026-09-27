from django.urls import path, re_path

from apps.blog import views
from apps.catalog.urls import UNICODE_SLUG

app_name = "blog"

urlpatterns = [
    path("", views.post_list, name="list"),
    re_path(rf"^(?P<slug>{UNICODE_SLUG})/$", views.post_detail, name="detail"),
]
