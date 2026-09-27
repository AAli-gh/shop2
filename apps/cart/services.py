from django.db import transaction
from django.utils import timezone

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


def _touch(cart: Cart) -> None:
    """Item changes don't save the cart row; record them for abandoned-cart reminders."""
    Cart.objects.filter(pk=cart.pk).update(updated_at=timezone.now())


def cart_summary(cart: Cart) -> dict:
    items = []
    subtotal = 0
    item_count = 0
    for item in cart.items.select_related("product", "variant"):
        unit_price = item.offer.effective_price
        line_total = unit_price * item.quantity
        subtotal += line_total
        item_count += item.quantity
        items.append({
            "item": item, "product": item.product, "variant": item.variant,
            "unit_price": unit_price, "line_total": line_total,
        })
    return {"items": items, "subtotal": subtotal, "item_count": item_count}


def add_to_cart(request, *, product_id: int, quantity: int = 1, variant_id: int | None = None) -> dict:
    product = Product.objects.filter(pk=product_id, is_active=True).first()
    if product is None:
        raise CartError("محصول یافت نشد")

    variant = None
    if product.has_variants:
        if not variant_id:
            raise CartError("ابتدا رنگ یا مدل را انتخاب کنید")
        variant = product.variants.filter(pk=variant_id, is_active=True).first()
        if variant is None:
            raise CartError("این مدل در دسترس نیست")
    offer = variant or product
    if offer.stock == 0:
        raise CartError("این محصول موجود نیست")

    quantity = max(1, quantity)
    cart = get_or_create_cart(request)

    with transaction.atomic():
        item, created = CartItem.objects.get_or_create(
            cart=cart, product=product, variant=variant, defaults={"quantity": quantity}
        )
        if not created:
            item.quantity = min(item.quantity + quantity, offer.stock)
        else:
            item.quantity = min(item.quantity, offer.stock)
        item.save()
        _touch(cart)

    return cart_summary(cart)


def update_item_quantity(request, *, item_id: int, quantity: int) -> dict:
    cart = get_or_create_cart(request)
    item = cart.items.filter(pk=item_id).select_related("product", "variant").first()
    if not item:
        raise CartError("ردیف سبد یافت نشد")

    # asking for more than is in stock (e.g. "+" on the last unit) keeps what is available, not nothing
    quantity = min(max(0, quantity), item.offer.stock)
    if quantity == 0:
        item.delete()
    else:
        item.quantity = quantity
        item.save()
    _touch(cart)
    return cart_summary(cart)


def remove_item(request, *, item_id: int) -> dict:
    cart = get_or_create_cart(request)
    cart.items.filter(pk=item_id).delete()
    _touch(cart)
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
            for item in guest_cart.items.select_related("product", "variant"):
                existing = user_cart.items.filter(product=item.product, variant=item.variant).first()
                if existing:
                    existing.quantity = min(existing.quantity + item.quantity, item.offer.stock or existing.quantity)
                    existing.save()
                else:
                    item.cart = user_cart
                    item.save()
                item.refresh_from_db()
            guest_cart.items.all().delete()
            guest_cart.delete()
            _touch(user_cart)

    request.session.pop("cart_id", None)
