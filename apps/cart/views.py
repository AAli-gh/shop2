from django.shortcuts import render

from apps.cart import services
from apps.cart.services import CartError


def detail(request):
    cart = services.get_or_create_cart(request)
    return render(request, "cart/cart.html", {"summary": services.cart_summary(cart)})


def _cart_page_response(request, summary, template="cart/partials/cart_with_badge.html"):
    return render(request, template, {"summary": summary})


def htmx_add(request, product_id):
    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1
    try:
        variant_id = int(request.POST.get("variant") or 0) or None
    except (TypeError, ValueError):
        variant_id = None
    try:
        summary = services.add_to_cart(request, product_id=product_id, quantity=quantity, variant_id=variant_id)
        added = next((row for row in summary["items"]
                      if row["product"].pk == product_id and row["item"].variant_id == variant_id), None)
        return render(request, "cart/partials/add_feedback.html", {
            "summary": summary,
            "added_product": added["product"] if added else None,
            "added_variant": added["variant"] if added else None,
            "added_quantity": quantity,
        })
    except CartError as exc:
        summary = services.cart_summary(services.get_or_create_cart(request))
        return render(request, "cart/partials/add_feedback.html", {"summary": summary, "error": str(exc)})


def htmx_update(request, item_id):
    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1
    summary = services.update_item_quantity(request, item_id=item_id, quantity=quantity)
    return _cart_page_response(request, summary)


def htmx_remove(request, item_id):
    summary = services.remove_item(request, item_id=item_id)
    return _cart_page_response(request, summary)
