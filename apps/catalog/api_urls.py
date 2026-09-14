from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.cart.api import CartViewSet
from apps.catalog.api import ProductViewSet
from apps.orders.api import MyOrderViewSet

app_name = "api"

router = DefaultRouter()
router.register("products", ProductViewSet, basename="product")
router.register("cart", CartViewSet, basename="cart")
router.register("me/orders", MyOrderViewSet, basename="my-order")

urlpatterns = [
    path("", include(router.urls)),
]
