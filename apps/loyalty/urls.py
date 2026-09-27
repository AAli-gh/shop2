from django.urls import path

from apps.loyalty import views

app_name = "loyalty"

urlpatterns = [
    path("", views.club_page, name="club"),
    path("redeem/", views.redeem, name="redeem"),
    path("referrer/", views.enter_code, name="enter_code"),
]
