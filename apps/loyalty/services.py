"""Customer club: points for delivered orders, turned into wallet credit, and friend referrals.

Points are earned only once an order is delivered, so cancelled orders never earn and a
return completed later takes the points of the refunded goods back. A referral pays both
sides when the new customer's first qualifying order is delivered, once per new customer.
All amounts come from SiteSettings so the shop can tune or switch off the club.
"""
from django.db import IntegrityError, transaction
from django.db.models import F

from apps.common.services import get_settings
from apps.loyalty.models import LoyaltyAccount, PointTransaction, new_referral_code

SESSION_REFERRAL = "referral_code"


class LoyaltyError(Exception):
    pass


def is_enabled() -> bool:
    return get_settings().loyalty_enabled


def get_account(user) -> LoyaltyAccount:
    account = LoyaltyAccount.objects.filter(user=user).first()
    if account is not None:
        return account
    for _ in range(5):  # a clash of random codes is rare; try another
        try:
            with transaction.atomic():
                account, _ = LoyaltyAccount.objects.get_or_create(user=user, defaults={"referral_code": new_referral_code()})
                return account
        except IntegrityError:
            continue
    raise LoyaltyError("ساخت کد معرف ناموفق بود؛ دوباره تلاش کنید.")


def normalize_code(raw) -> str:
    return "".join(str(raw or "").split()).upper()[:12]


def _add(account: LoyaltyAccount, kind: str, points: int, *, order=None, note: str = "") -> PointTransaction:
    LoyaltyAccount.objects.filter(pk=account.pk).update(points=F("points") + points)
    return PointTransaction.objects.create(account=account, kind=kind, points=points, order=order, note=note)


def points_for_amount(amount: int) -> int:
    settings_obj = get_settings()
    if not settings_obj.loyalty_enabled or amount <= 0:
        return 0
    return amount // settings_obj.loyalty_toman_per_point


def order_points(order) -> int:
    """Points an order earns: goods after discount; shipping and install don't count."""
    return points_for_amount(order.items_subtotal - order.discount_amount)


# ---------------------------------------------------------------- orders

def order_delivered(order) -> None:
    """Credit purchase points and, for a referred customer's first qualifying order, both referral rewards.

    Called inside the delivery transaction; safe to call again for the same order.
    """
    if not is_enabled() or order.sales_rep_id:
        return  # a rep's order is the company's sale to a shop, not the rep's own purchase
    account = get_account(order.user)
    account = LoyaltyAccount.objects.select_for_update().get(pk=account.pk)

    points = order_points(order)
    if points and not PointTransaction.objects.filter(account=account, order=order, kind=PointTransaction.Kind.PURCHASE).exists():
        _add(account, PointTransaction.Kind.PURCHASE, points, order=order)

    _reward_referral(account, order)


def _reward_referral(account: LoyaltyAccount, order) -> None:
    settings_obj = get_settings()
    if account.referred_by_id is None or account.referral_rewarded:
        return
    if order.items_subtotal - order.discount_amount < settings_obj.referral_min_order_amount:
        return  # a later, bigger order can still qualify
    referrer = get_account(account.referred_by)
    if settings_obj.referral_referrer_points:
        _add(referrer, PointTransaction.Kind.REFERRAL, settings_obj.referral_referrer_points, order=order,
             note=f"خرید {account.user}")
    if settings_obj.referral_friend_points:
        _add(account, PointTransaction.Kind.WELCOME, settings_obj.referral_friend_points, order=order)
    LoyaltyAccount.objects.filter(pk=account.pk).update(referral_rewarded=True)


def goods_returned(return_request) -> int:
    """Take back the points earned on refunded goods; returns the points removed.

    Never more than the order earned, and the balance may go negative if they were already spent.
    """
    order = return_request.order
    earned = PointTransaction.objects.filter(order=order, kind=PointTransaction.Kind.PURCHASE).first()
    if earned is None or not return_request.refund_amount:
        return 0
    already = -sum(
        PointTransaction.objects.filter(order=order, kind=PointTransaction.Kind.RETURN).values_list("points", flat=True)
    )
    settings_obj = get_settings()
    take = min(return_request.refund_amount // settings_obj.loyalty_toman_per_point, earned.points - already)
    if take <= 0:
        return 0
    account = LoyaltyAccount.objects.select_for_update().get(pk=earned.account_id)
    _add(account, PointTransaction.Kind.RETURN, -take, order=order)
    return take


# ---------------------------------------------------------------- redeeming

def redeem(*, user, points: int) -> int:
    """Turn points into wallet credit; returns the Toman credited."""
    from apps.wallet.models import Wallet, WalletTransaction
    from apps.wallet.services import get_wallet

    settings_obj = get_settings()
    if not settings_obj.loyalty_enabled:
        raise LoyaltyError("باشگاه مشتریان فعال نیست.")
    if points < settings_obj.loyalty_min_redeem_points:
        raise LoyaltyError(f"دست‌کم {settings_obj.loyalty_min_redeem_points:,} امتیاز را می‌توانید یک‌جا تبدیل کنید.")

    with transaction.atomic():
        account = LoyaltyAccount.objects.select_for_update().get(pk=get_account(user).pk)
        if points > account.points:
            raise LoyaltyError("امتیاز شما کافی نیست.")
        amount = points * settings_obj.loyalty_point_value
        _add(account, PointTransaction.Kind.REDEEM, -points, note=f"{amount:,} تومان")
        wallet = get_wallet(user)
        Wallet.objects.filter(pk=wallet.pk).update(balance=F("balance") + amount)
        WalletTransaction.objects.create(wallet=wallet, kind=WalletTransaction.Kind.LOYALTY, amount=amount)
    return amount


# ---------------------------------------------------------------- referrals

def remember_referral(request) -> None:
    """Keep ?ref=CODE from a shared link until the visitor signs up."""
    code = normalize_code(request.GET.get("ref"))
    if code and not request.user.is_authenticated:
        request.session[SESSION_REFERRAL] = code


def can_enter_referral_code(user) -> bool:
    """Only new customers can name a referrer: nobody set yet and no order placed."""
    from apps.orders.models import Order

    account = get_account(user)
    return account.referred_by_id is None and not (
        Order.objects.filter(user=user).exclude(status=Order.Status.CANCELLED).exists()
    )


def set_referrer(*, user, code: str) -> LoyaltyAccount:
    code = normalize_code(code)
    if not can_enter_referral_code(user):
        raise LoyaltyError("کد معرف فقط پیش از اولین خرید ثبت می‌شود.")
    referrer = LoyaltyAccount.objects.filter(referral_code=code).select_related("user").first()
    if referrer is None:
        raise LoyaltyError("کد معرف پیدا نشد.")
    if referrer.user_id == user.pk:
        raise LoyaltyError("نمی‌توانید کد خودتان را وارد کنید.")
    if referrer.referred_by_id == user.pk:
        raise LoyaltyError("کسی که شما معرفی کرده‌اید نمی‌تواند معرف شما باشد.")
    account = get_account(user)
    LoyaltyAccount.objects.filter(pk=account.pk, referred_by__isnull=True).update(referred_by=referrer.user)
    account.refresh_from_db()
    return account


def attach_referral_from_session(request, user) -> None:
    """After sign-up: link the account to the referrer whose link brought the visitor, if any."""
    code = request.session.pop(SESSION_REFERRAL, "")
    if code and is_enabled():
        try:
            set_referrer(user=user, code=code)
        except LoyaltyError:
            pass  # an invalid or own code from a link is simply ignored
