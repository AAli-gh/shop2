"""«معمولاً با هم خریده می‌شوند» — learned from the shop's own paid orders.

For a product, the products that appeared in the same orders, most often first. Nothing is
invented: with no shared orders yet the section simply doesn't appear, so the page never
claims a connection that the sales don't show.
"""
from django.core.cache import cache
from django.db.models import Count

CACHE_SECONDS = 6 * 60 * 60
LIMIT = 4


def _paid_statuses():
    from apps.orders.models import Order

    return [Order.Status.PAID, Order.Status.PROCESSING, Order.Status.SHIPPED, Order.Status.DELIVERED]


def _companion_ids(product_ids, limit) -> list[int]:
    """Product ids most often bought in the same order as any of `product_ids`."""
    from apps.orders.models import OrderItem

    rows = (
        OrderItem.objects.filter(order__status__in=_paid_statuses(), order__items__product_id__in=product_ids)
        .exclude(product_id__in=product_ids)
        .filter(product__isnull=False)
        .values("product_id")
        .annotate(orders=Count("order_id", distinct=True))
        .order_by("-orders", "-product_id")[:limit]
    )
    return [row["product_id"] for row in rows]


def _products_in_order(ids):
    from apps.catalog.services import _active_qs

    if not ids:
        return []
    products = {p.pk: p for p in _active_qs().filter(pk__in=ids, stock__gt=0)}
    return [products[pk] for pk in ids if pk in products]


def bought_together(product, limit: int = LIMIT):
    """Companions of one product; cached, since the answer only changes as orders come in."""
    key = f"bought_together:{product.pk}:{limit}"
    ids = cache.get(key)
    if ids is None:
        ids = _companion_ids([product.pk], limit * 2)  # extra ids in case some are inactive or sold out
        cache.set(key, ids, CACHE_SECONDS)
    return _products_in_order(ids)[:limit]


def bought_together_with_cart(cart, limit: int = LIMIT):
    """Companions of everything in the cart, leaving out what is already in it."""
    in_cart = list(cart.items.values_list("product_id", flat=True))
    if not in_cart:
        return []
    return _products_in_order(_companion_ids(in_cart, limit * 2))[:limit]
