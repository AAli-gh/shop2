import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.catalog.models import Product
from apps.common.services import get_settings
from apps.discounts import services as discount_services
from apps.discounts.models import Coupon
from apps.orders.models import Order, OrderItem, ShippingAddress


class OrderError(Exception):
    def __init__(self, message, code="order_error"):
        super().__init__(message)
        self.code = code


class EmptyCartError(OrderError):
    def __init__(self):
        super().__init__("سبد خرید شما خالی است.", code="empty_cart")


class OutOfStockError(OrderError):
    def __init__(self, product_name=""):
        msg = f"موجودی «{product_name}» کافی نیست." if product_name else "موجودی کافی نیست."
        super().__init__(msg, code="out_of_stock")


class InvalidCouponError(OrderError):
    def __init__(self, message):
        super().__init__(message, code="invalid_coupon")


def generate_order_number() -> str:
    while True:
        number = f"SH-{uuid.uuid4().hex[:8].upper()}"
        if not Order.objects.filter(order_number=number).exists():
            return number


def compute_shipping(subtotal: int) -> int:
    settings_obj = get_settings()
    threshold = settings_obj.free_shipping_threshold
    if threshold is not None and subtotal >= threshold:
        return 0
    return settings_obj.shipping_flat_rate


def resolve_shipping(subtotal: int, shipping_method=None) -> int:
    """Cost of the chosen shipping method, honouring the free-shipping threshold."""
    if shipping_method is not None:
        settings_obj = get_settings()
        threshold = settings_obj.free_shipping_threshold
        if threshold is not None and subtotal >= threshold:
            return 0
        return shipping_method.price
    return compute_shipping(subtotal)


def checkout_context_data(user, cart_summary: dict, coupon_result=None, *,
                          shipping_method=None, install_needed=False) -> dict:
    subtotal = cart_summary["subtotal"]
    discount = coupon_result.discount_amount if coupon_result and not coupon_result.error else 0
    shipping = resolve_shipping(subtotal, shipping_method)
    settings_obj = get_settings()
    install = settings_obj.install_fee if install_needed else 0
    total = subtotal - discount + shipping + install
    balance = 0
    wallet = None
    if user.is_authenticated:
        from apps.wallet.models import Wallet

        wallet = Wallet.objects.filter(user=user).first()
        balance = wallet.balance if wallet else 0
    return {
        "subtotal": subtotal,
        "discount": discount,
        "shipping": shipping,
        "install": install,
        "total": total,
        "wallet_balance": balance,
    }


def apply_coupon_to_session(request, *, code: str, subtotal: int):
    result = discount_services.validate_coupon(code=code, subtotal=subtotal)
    if result.error:
        request.session.pop("coupon_code", None)
    else:
        request.session["coupon_code"] = result.coupon.code
    return result


def place_order(*, user, cart, address_data: dict, coupon_code: str = "",
                shipping_method=None, install_requested=False, install_date: str = "",
                pay_with_wallet=False) -> Order:
    from apps.wallet.services import WalletError, debit_for_order, get_wallet

    with transaction.atomic():
        items = list(cart.items.select_related("product"))
        if not items:
            raise EmptyCartError()

        product_ids = [item.product_id for item in items]
        products = {
            p.pk: p
            for p in Product.objects.select_for_update().filter(pk__in=product_ids)
        }

        # validate stock + authoritative prices
        subtotal = 0
        lines = []
        for item in items:
            product = products.get(item.product_id)
            if product is None or not product.is_active:
                raise OutOfStockError(item.product.name if product else "")
            if item.quantity > product.stock:
                raise OutOfStockError(product.name)
            line_total = product.effective_price * item.quantity
            subtotal += line_total
            lines.append({
                "product": product,
                "product_name": product.name,
                "unit_price": product.effective_price,
                "quantity": item.quantity,
                "line_total": line_total,
            })

        # coupon: conditional increment is the race guard
        discount = 0
        coupon = None
        coupon_code = (coupon_code or "").strip().upper()
        if coupon_code:
            result = discount_services.validate_coupon(code=coupon_code, subtotal=subtotal)
            if result.error:
                raise InvalidCouponError(discount_services.error_message(result.error))
            coupon = result.coupon
            discount = result.discount_amount
            rows = (
                Coupon.objects.filter(pk=coupon.pk, is_active=True)
                .filter(Q(usage_limit__isnull=True) | Q(used_count__lt=F("usage_limit")))
                .update(used_count=F("used_count") + 1)
            )
            if rows == 0:
                raise InvalidCouponError(discount_services.error_message("usage_limit_reached"))

        settings_obj = get_settings()
        shipping = resolve_shipping(subtotal, shipping_method)
        install = settings_obj.install_fee if install_requested else 0
        total = subtotal - discount + shipping + install

        order = Order.objects.create(
            order_number=generate_order_number(),
            user=user,
            status=Order.Status.PENDING_PAYMENT,
            items_subtotal=subtotal,
            discount_amount=discount,
            shipping_cost=shipping,
            total=total,
            coupon=coupon,
            coupon_code=coupon.code if coupon else "",
            shipping_method=shipping_method,
            install_requested=install_requested,
            install_cost=install,
            install_date=install_date,
        )
        ShippingAddress.objects.create(order=order, **address_data)

        for line in lines:
            OrderItem.objects.create(order=order, **line)

        # decrement stock with conditional update; abort placement if any fails
        for line in lines:
            updated = Product.objects.filter(
                pk=line["product"].pk, stock__gte=line["quantity"]
            ).update(stock=F("stock") - line["quantity"], sold_count=F("sold_count") + line["quantity"])
            if updated == 0:
                raise OutOfStockError(line["product_name"])

        cart.items.all().delete()

        # pay from wallet inside the same transaction so a failure rolls everything back
        if pay_with_wallet and total > 0:
            try:
                debit_for_order(user=user, order=order, amount=total)
            except WalletError as exc:
                raise OrderError(str(exc), code="wallet")
            order.wallet_used = total
            order.status = Order.Status.PAID
            order.payment_ref = "WALLET"
            order.save(update_fields=["wallet_used", "status", "payment_ref"])

    from apps.common import shoplog
    from apps.orders.emails import order_placed

    shoplog.order_placed(order)
    order_placed(order)
    return order


def _release_reservations(order: Order) -> None:
    """Give back the stock and coupon use an order reserved (caller holds the order lock)."""
    for item in order.items.all():
        if item.product_id:
            Product.objects.filter(pk=item.product_id).update(
                stock=F("stock") + item.quantity,
                sold_count=F("sold_count") - item.quantity,
            )

    if order.coupon_id:
        Coupon.objects.filter(pk=order.coupon_id, used_count__gt=0).update(
            used_count=F("used_count") - 1
        )


def _refund_wallet_payment(order: Order) -> None:
    """Wallet money never left the shop, so cancelling returns it automatically."""
    if order.wallet_used:
        from apps.wallet.services import charge_from_order_refund

        charge_from_order_refund(user=order.user, order=order, amount=order.wallet_used)


def needs_manual_refund(order: Order) -> bool:
    """True for a cancelled order paid (partly) through a bank gateway: finance must return that money."""
    return (
        order.status == Order.Status.CANCELLED
        and bool(order.payment_ref)
        and order.total > order.wallet_used
    )


@transaction.atomic
def cancel_pending_order(*, order: Order) -> Order:
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status != Order.Status.PENDING_PAYMENT:
        raise OrderError("فقط سفارش در انتظار پرداخت قابل لغو است.")

    _release_reservations(order)
    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status", "updated_at"])

    from apps.common import shoplog

    shoplog.order_cancelled(order)
    return order


def expire_unpaid_orders(*, older_than_minutes: int | None = None, now=None, dry_run: bool = False) -> list[str]:
    """Cancel orders left unpaid past the payment window so their stock and coupons free up.

    An order whose gateway payment started within ORDER_PAYMENT_GRACE_MINUTES is skipped:
    the customer may still be on the bank page. Returns the affected order numbers.
    """
    from apps.common import shoplog
    from apps.orders.emails import order_status_changed
    from apps.payments.models import Payment

    now = now or timezone.now()
    minutes = settings.ORDER_PAYMENT_TIMEOUT_MINUTES if older_than_minutes is None else older_than_minutes
    payment_in_progress = Payment.objects.filter(
        status=Payment.Status.CREATED,
        created_at__gte=now - timedelta(minutes=settings.ORDER_PAYMENT_GRACE_MINUTES),
    ).values("order_id")
    candidates = (
        Order.objects.filter(
            status=Order.Status.PENDING_PAYMENT,
            created_at__lt=now - timedelta(minutes=minutes),
        )
        .exclude(pk__in=payment_in_progress)
        .order_by("created_at")
    )

    expired = []
    for order in candidates:
        if dry_run:
            expired.append(order.order_number)
            continue
        try:
            order = cancel_pending_order(order=order)
        except OrderError:
            continue  # paid or cancelled since the query ran
        shoplog.order_expired(order)
        order_status_changed(order)
        expired.append(order.order_number)
    return expired


ALLOWED_TRANSITIONS = {
    Order.Status.PENDING_PAYMENT: {Order.Status.PAID, Order.Status.CANCELLED},
    Order.Status.PAID: {Order.Status.PROCESSING, Order.Status.CANCELLED},
    Order.Status.PROCESSING: {Order.Status.SHIPPED},
    Order.Status.SHIPPED: {Order.Status.DELIVERED},
    Order.Status.DELIVERED: set(),
    Order.Status.CANCELLED: set(),
}


@transaction.atomic
def transition_status(*, order: Order, new_status: str) -> Order:
    order = Order.objects.select_for_update().get(pk=order.pk)
    if new_status not in ALLOWED_TRANSITIONS.get(order.status, set()):
        raise OrderError(f"تغییر وضعیت از «{order.get_status_display()}» به «{Order.Status(new_status).label}» مجاز نیست.")
    old_status = order.status
    update_fields = ["status", "updated_at"]
    if new_status == Order.Status.CANCELLED:
        # same bookkeeping as a customer cancellation, plus returning wallet money
        _release_reservations(order)
        _refund_wallet_payment(order)
    elif new_status == Order.Status.DELIVERED:
        order.delivered_at = timezone.now()  # the return window counts from here
        update_fields.append("delivered_at")
    order.status = new_status
    order.save(update_fields=update_fields)

    from apps.common import shoplog
    from apps.orders.emails import order_status_changed

    shoplog.order_status_changed(order, old_status)
    if new_status == Order.Status.CANCELLED:
        shoplog.order_cancelled(order)
        if needs_manual_refund(order):
            shoplog.refund_required(order)
    order_status_changed(order)
    return order


def get_user_order(user, order_number: str) -> Order:
    return Order.objects.filter(order_number=order_number, user=user).first()
