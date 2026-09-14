from django.urls import path

from apps.payments import views

app_name = "payments"

urlpatterns = [
    path("callback/<str:order_number>/", views.callback, name="callback"),
]
