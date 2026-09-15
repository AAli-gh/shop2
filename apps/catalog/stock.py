"""Stock bookkeeping shared by checkout, cancellations and returns — with or without variants."""
from django.db.models import F, Value
from django.db.models.functions import Greatest

from apps.catalog.models import Product, ProductVariant


def sync_variant_totals(product_id) -> None:
    """Mirror a variant product's sellable options onto the product row: cheapest prices, total stock.

    When every variant is switched off the product gets stock 0, so it can't be sold as a plain
    product with stale numbers. A product that never had variants is left alone.
    """
    variants = list(
        ProductVariant.objects.filter(product_id=product_id).values("price", "sale_price", "stock", "is_active")
    )
    if not variants:
        return
    active = [v for v in variants if v["is_active"]]
    if not active:
        Product.objects.filter(pk=product_id).update(stock=0)
        return
    cheapest = min(
        active, key=lambda v: (v["sale_price"] if v["sale_price"] is not None else v["price"], v["price"])
    )
    Product.objects.filter(pk=product_id).update(
        price=cheapest["price"], sale_price=cheapest["sale_price"], stock=sum(v["stock"] for v in active),
    )


def take_stock(*, product_id, variant_id, quantity: int) -> int | None:
    """Remove sold units with a conditional update; the stock left afterwards, or None if there weren't enough."""
    if variant_id:
        taken = ProductVariant.objects.filter(pk=variant_id, stock__gte=quantity).update(stock=F("stock") - quantity)
        if not taken:
            return None
        Product.objects.filter(pk=product_id).update(sold_count=F("sold_count") + quantity)
        sync_variant_totals(product_id)
        return ProductVariant.objects.values_list("stock", flat=True).get(pk=variant_id)

    taken = Product.objects.filter(pk=product_id, stock__gte=quantity).update(
        stock=F("stock") - quantity, sold_count=F("sold_count") + quantity,
    )
    if not taken:
        return None
    return Product.objects.values_list("stock", flat=True).get(pk=product_id)


def give_back_stock(*, product_id, variant_id, quantity: int) -> None:
    """Undo take_stock, for a cancelled order or goods that came back."""
    Product.objects.filter(pk=product_id).update(sold_count=Greatest(F("sold_count") - quantity, Value(0)))
    if variant_id and ProductVariant.objects.filter(pk=variant_id).update(stock=F("stock") + quantity):
        sync_variant_totals(product_id)
    else:
        Product.objects.filter(pk=product_id).update(stock=F("stock") + quantity)
