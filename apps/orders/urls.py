from django.urls import path

from apps.orders import views

app_name = "orders"

urlpatterns = [
    path("checkout/", views.CheckoutView.as_view(), name="checkout"),
    path("checkout/coupon/", views.CouponApplyView.as_view(), name="coupon_apply"),
    path("checkout/place/", views.PlaceOrderView.as_view(), name="place"),
    path("checkout/pay/<str:order_number>/", views.PayView.as_view(), name="pay"),
    path("orders/", views.OrderListView.as_view(), name="list"),
    # before orders/<order_number>/ so "returns" isn't read as an order number
    path("orders/returns/", views.ReturnRequestListView.as_view(), name="returns"),
    path("orders/<str:order_number>/", views.OrderDetailView.as_view(), name="detail"),
    path("orders/<str:order_number>/invoice/", views.InvoiceView.as_view(), name="invoice"),
    path("orders/<str:order_number>/return/", views.ReturnRequestCreateView.as_view(), name="return_create"),
    path("orders/<str:order_number>/success/", views.OrderSuccessView.as_view(), name="success"),
    path("orders/<str:order_number>/cancel/", views.OrderCancelView.as_view(), name="cancel"),
]
