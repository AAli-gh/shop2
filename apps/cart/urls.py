from django.urls import path

from apps.cart import views

app_name = "cart"

urlpatterns = [
    path("", views.detail, name="detail"),
    path("htmx/add/<int:product_id>/", views.htmx_add, name="htmx_add"),
    path("htmx/item/<int:item_id>/update/", views.htmx_update, name="htmx_update"),
    path("htmx/item/<int:item_id>/remove/", views.htmx_remove, name="htmx_remove"),
]
