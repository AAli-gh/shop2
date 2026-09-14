from django.urls import path

from apps.wishlist import views

app_name = "wishlist"

urlpatterns = [
    path("", views.wishlist_page, name="list"),
    path("htmx/toggle/<int:product_id>/", views.htmx_toggle, name="toggle"),
]
