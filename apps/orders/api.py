from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.orders.models import Order, OrderItem


class OrderItemInlineSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ["product_name", "unit_price", "quantity", "line_total"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemInlineSerializer(many=True, read_only=True)
    shipping_address = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id", "order_number", "status", "items_subtotal", "discount_amount",
            "shipping_cost", "total", "coupon_code", "payment_ref",
            "created_at", "items", "shipping_address",
        ]
        read_only_fields = fields

    def get_shipping_address(self, obj):
        addr = getattr(obj, "shipping_address", None)
        if not addr:
            return None
        return {
            "full_name": addr.full_name,
            "phone": addr.phone,
            "province": addr.province,
            "city": addr.city,
            "address_line": addr.address_line,
        }


class MyOrderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "order_number"

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user)
