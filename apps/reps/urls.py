from django.urls import path

from apps.reps import views

app_name = "reps"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("products/", views.products, name="products"),
    path("products/<int:pk>/", views.product_sheet, name="product"),
    path("basket/", views.basket, name="basket"),
    path("basket/add/", views.basket_add, name="basket_add"),
    path("orders/", views.orders, name="orders"),
    path("orders/<str:order_number>/", views.order_detail, name="order_detail"),
    path("orders/<str:order_number>/cancel/", views.order_cancel, name="order_cancel"),
    path("orders/<str:order_number>/reorder/", views.order_reorder, name="order_reorder"),
    path("customers/", views.customers, name="customers"),
    path("customers/new/", views.customer_form, name="customer_new"),
    path("customers/<int:pk>/edit/", views.customer_form, name="customer_edit"),
]
