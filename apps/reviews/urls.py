from django.urls import path

from apps.reviews import views

app_name = "reviews"

urlpatterns = [
    path("product/<int:product_id>/submit/", views.htmx_submit, name="submit"),
]
