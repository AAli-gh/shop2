from apps.catalog.models import Product
from apps.wishlist.models import WishlistItem


class WishlistError(Exception):
    pass


def toggle(request, *, product_id: int) -> dict:
    """Add or remove a product from the user's wishlist. Returns state + count."""
    user = request.user
    if not user.is_authenticated:
        raise WishlistError("برای استفاده از علاقه‌مندی‌ها وارد شوید.")

    try:
        product = Product.objects.get(pk=product_id, is_active=True)
    except Product.DoesNotExist:
        raise WishlistError("محصول یافت نشد")

    existing = WishlistItem.objects.filter(user=user, product=product).first()
    if existing:
        existing.delete()
        active = False
    else:
        WishlistItem.objects.create(user=user, product=product)
        active = True

    return {
        "product_id": product.pk,
        "active": active,
        "count": WishlistItem.objects.filter(user=user).count(),
    }


def wishlist_for(user):
    return (
        WishlistItem.objects.filter(user=user, product__is_active=True)
        .select_related("product", "product__category")
    )


def count_for(user) -> int:
    if not user.is_authenticated:
        return 0
    return WishlistItem.objects.filter(user=user, product__is_active=True).count()
