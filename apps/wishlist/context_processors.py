from apps.wishlist.models import WishlistItem


def wishlist(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"wishlist_count": 0, "wishlist_ids": set()}
    ids = set(
        WishlistItem.objects.filter(user=user, product__is_active=True)
        .values_list("product_id", flat=True)
    )
    return {"wishlist_count": len(ids), "wishlist_ids": ids}
