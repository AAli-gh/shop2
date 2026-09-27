from dataclasses import dataclass

from django.utils import timezone

from apps.discounts.models import Coupon


@dataclass
class CouponResult:
    coupon: Coupon | None
    discount_amount: int
    error: str | None = None


ERROR_MESSAGES = {
    "not_found": "کد تخفیف یافت نشد.",
    "inactive": "این کد تخفیف فعال نیست.",
    "expired": "این کد تخفیف منقضی شده است.",
    "not_started": "این کد تخفیف هنوز فعال نشده است.",
    "usage_limit_reached": "ظرفیت استفاده از این کد تکمیل شده است.",
    "min_order_not_met": "مبلغ سبد خرید برای استفاده از این کد کافی نیست.",
    "login_required": "برای استفاده از این کد ابتدا وارد حساب خود شوید.",
    "per_user_limit_reached": "سهم شما از این کد تخفیف قبلاً استفاده شده است.",
    "first_order_only": "این کد تخفیف فقط برای اولین خرید است.",
}


def _customer_orders(user):
    """The customer's orders that count as purchases: everything except cancelled ones."""
    from apps.orders.models import Order

    return Order.objects.filter(user=user).exclude(status=Order.Status.CANCELLED)


def validate_coupon(*, code: str, subtotal: int, user=None) -> CouponResult:
    """Check a code for this basket; `user` is the buyer (needed for per-customer rules)."""
    code = (code or "").strip().upper()
    coupon = Coupon.objects.filter(code=code).first()
    if coupon is None:
        return CouponResult(None, 0, "not_found")
    if not coupon.is_active:
        return CouponResult(None, 0, "inactive")
    now = timezone.now()
    if coupon.valid_from and now < coupon.valid_from:
        return CouponResult(None, 0, "not_started")
    if coupon.valid_to and now > coupon.valid_to:
        return CouponResult(None, 0, "expired")
    if coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit:
        return CouponResult(None, 0, "usage_limit_reached")
    if subtotal < coupon.min_order_amount:
        return CouponResult(None, 0, "min_order_not_met")
    if coupon.per_user_limit is not None or coupon.first_order_only:
        if not getattr(user, "is_authenticated", False):
            return CouponResult(None, 0, "login_required")
        if coupon.first_order_only and _customer_orders(user).exists():
            return CouponResult(None, 0, "first_order_only")
        if coupon.per_user_limit is not None and _customer_orders(user).filter(coupon=coupon).count() >= coupon.per_user_limit:
            return CouponResult(None, 0, "per_user_limit_reached")

    if coupon.kind == Coupon.Kind.PERCENT:
        discount = subtotal * coupon.value // 100
        if coupon.max_discount_amount is not None:
            discount = min(discount, coupon.max_discount_amount)
    else:
        discount = min(coupon.value, subtotal)
    return CouponResult(coupon, discount, None)


def error_message(error_code: str) -> str:
    return ERROR_MESSAGES.get(error_code, "کد تخفیف معتبر نیست.")
