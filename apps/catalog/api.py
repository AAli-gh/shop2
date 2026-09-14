from django.db.models import Q
from rest_framework import serializers, viewsets

from apps.catalog.models import Product


class ProductSerializer(serializers.ModelSerializer):
    category = serializers.StringRelatedField(read_only=True)
    price_toman = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "slug", "name", "description", "category", "price",
            "price_toman", "stock", "is_active", "image", "created_at",
        ]
        read_only_fields = fields

    def get_price_toman(self, obj):
        return f"{obj.price:,} تومان"


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = (
        Product.objects.filter(is_active=True)
        .select_related("category")
        .order_by("-created_at")
    )
    serializer_class = ProductSerializer
    lookup_field = "slug"
    filterset_fields = []
    search_fields = []

    def get_queryset(self):
        qs = super().get_queryset()
        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(
                Q(category__slug=category) | Q(category__parent__slug=category)
            )
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
        ordering = self.request.query_params.get("ordering")
        if ordering in {"price", "-price", "created_at", "-created_at"}:
            qs = qs.order_by(ordering)
        return qs
