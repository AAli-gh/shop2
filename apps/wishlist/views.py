from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.wishlist import services
from apps.wishlist.services import WishlistError


@login_required
def wishlist_page(request):
    return render(
        request,
        "wishlist/wishlist.html",
        {"items": services.wishlist_for(request.user)},
    )


def htmx_toggle(request, product_id):
    try:
        result = services.toggle(request, product_id=product_id)
        error = None
    except WishlistError as exc:
        result = {"product_id": product_id, "active": False, "count": services.count_for(request.user)}
        error = str(exc)

    response = render(
        request,
        "wishlist/partials/heart_button.html",
        {"product_id": product_id, "active": result["active"], "error": error, "for_htmx": True},
    )
    return response
