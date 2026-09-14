from django.db import transaction

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Product


class CartError(Exception):
    pass


def get_or_create_cart(request) -> Cart:
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
        return cart

    cart_id = request.session.get("cart_id")
    if cart_id:
        cart = Cart.objects.filter(pk=cart_id, user__isnull=True).first()
        if cart:
            return cart
    if not request.session.session_key:
        request.session.cycle_key()
    cart = Cart.objects.create(session_key=request.session.session_key)
    request.session["cart_id"] = cart.pk
    return cart


def cart_summary(cart: Cart) -> dict:
    items = []
    subtotal = 0
    item_count = 0
    for item in cart.items.select_related("product"):
        line_total = item.product.effective_price * item.quantity
        subtotal += line_total
        item_count += item.quantity
        items.append({"item": item, "product": item.product, "line_total": line_total})
    return {"items": items, "subtotal": subtotal, "item_count": item_count}


def add_to_cart(request, *, product_id: int, quantity: int = 1) -> dict:
    try:
        product = Product.objects.get(pk=product_id, is_active=True)
    except Product.DoesNotExist:
        raise CartError("محصول یافت نشد")

    if product.stock == 0:
        raise CartError("این محصول موجود نیست")

    quantity = max(1, quantity)
    cart = get_or_create_cart(request)

    with transaction.atomic():
        item, created = CartItem.objects.get_or_create(
            cart=cart, product=product, defaults={"quantity": quantity}
        )
        if not created:
            item.quantity = min(item.quantity + quantity, product.stock)
        else:
            item.quantity = min(item.quantity, product.stock)
        item.save()

    return cart_summary(cart)


def update_item_quantity(request, *, item_id: int, quantity: int) -> dict:
    cart = get_or_create_cart(request)
    item = cart.items.filter(pk=item_id).select_related("product").first()
    if not item:
        raise CartError("ردیف سبد یافت نشد")

    quantity = max(0, quantity)
    if quantity == 0 or quantity > item.product.stock:
        item.delete()
    else:
        item.quantity = quantity
        item.save()
    return cart_summary(cart)


def remove_item(request, *, item_id: int) -> dict:
    cart = get_or_create_cart(request)
    cart.items.filter(pk=item_id).delete()
    return cart_summary(cart)


def clear_cart(request) -> None:
    cart = get_or_create_cart(request)
    cart.items.all().delete()


def merge_carts(request, user) -> None:
    guest_cart_id = request.session.get("cart_id")
    user_cart = Cart.objects.filter(user=user).first()

    if not guest_cart_id:
        return

    guest_cart = Cart.objects.filter(pk=guest_cart_id, user__isnull=True).first()
    if not guest_cart:
        request.session.pop("cart_id", None)
        return

    with transaction.atomic():
        if user_cart is None:
            guest_cart.user = user
            guest_cart.session_key = None
            guest_cart.save()
        else:
            for item in guest_cart.items.select_related("product"):
                existing = user_cart.items.filter(product=item.product).first()
                if existing:
                    existing.quantity = min(
                        existing.quantity + item.quantity, item.product.stock or existing.quantity
                    )
                    existing.save()
                else:
                    item.cart = user_cart
                    item.save()
                item.refresh_from_db()
            guest_cart.items.all().delete()
            guest_cart.delete()

    request.session.pop("cart_id", None)
