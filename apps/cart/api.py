from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.cart import services
from apps.cart.models import Cart, CartItem
from apps.cart.services import CartError
from apps.catalog.models import Product


class CartItemSerializer(serializers.ModelSerializer):
    product = serializers.SerializerMethodField()
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ["id", "product", "product_id", "quantity", "line_total"]

    def get_product(self, obj):
        return {"slug": obj.product.slug, "name": obj.product.name, "price": obj.product.price}

    def get_line_total(self, obj):
        return obj.product.price * obj.quantity


class CartSerializer(serializers.Serializer):
    items = CartItemSerializer(many=True, read_only=True, source="items.all")
    subtotal = serializers.SerializerMethodField()
    item_count = serializers.SerializerMethodField()

    def get_subtotal(self, cart):
        return services.cart_summary(cart)["subtotal"]

    def get_item_count(self, cart):
        return services.cart_summary(cart)["item_count"]


def _summary_json(summary: dict) -> dict:
    return {
        "items": [
            {
                "product_id": row["product"].pk,
                "name": row["product"].name,
                "price": row["product"].price,
                "quantity": row["item"].quantity,
                "line_total": row["line_total"],
            }
            for row in summary["items"]
        ],
        "subtotal": summary["subtotal"],
        "item_count": summary["item_count"],
    }


class CartViewSet(viewsets.ViewSet):
    """Session/user based cart API (guest carts work too)."""

    permission_classes = [AllowAny]

    def _cart(self, request):
        return services.get_or_create_cart(request)

    def list(self, request):
        return Response(CartSerializer(self._cart(request)).data)

    @action(detail=False, methods=["post"], url_path="items")
    def create_item(self, request):
        serializer = AddItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            summary = services.add_to_cart(
                request,
                product_id=serializer.validated_data["product_id"],
                quantity=serializer.validated_data.get("quantity", 1),
            )
        except CartError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_summary_json(summary), status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["patch", "delete"], url_path=r"items/(?P<item_id>\d+)")
    def item_detail(self, request, item_id=None):
        if request.method == "DELETE":
            summary = services.remove_item(request, item_id=item_id)
            return Response(_summary_json(summary))
        serializer = UpdateItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            summary = services.update_item_quantity(
                request, item_id=item_id, quantity=serializer.validated_data["quantity"]
            )
        except CartError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_summary_json(summary))


class AddItemSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)


class UpdateItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=0)
