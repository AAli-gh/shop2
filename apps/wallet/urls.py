from django.urls import path

from apps.wallet import views

app_name = "wallet"

urlpatterns = [
    path("", views.wallet_page, name="page"),
    path("redeem/", views.redeem_code, name="redeem"),
]
