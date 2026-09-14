from django.db import transaction
from django.db.models import F

from apps.wallet.models import GiftCard, GiftCardRedemption, Wallet, WalletTransaction


class WalletError(Exception):
    pass


def get_wallet(user) -> Wallet:
    wallet, _ = Wallet.objects.get_or_create(user=user)
    return wallet


def redeem_gift_card(*, user, code: str) -> dict:
    code = (code or "").strip().upper()
    card = GiftCard.objects.filter(code=code).first()
    if card is None:
        raise WalletError("کد هدیه یافت نشد.")
    if not card.is_active:
        raise WalletError("این کد هدیه غیرفعال است.")
    if card.remaining <= 0:
        raise WalletError("اعتبار این کد هدیه تمام شده است.")
    if GiftCardRedemption.objects.filter(gift_card=card, user=user).exists():
        raise WalletError("شما قبلاً این کد را استفاده کرده‌اید.")

    with transaction.atomic():
        card = GiftCard.objects.select_for_update().get(pk=card.pk)
        if card.remaining <= 0:
            raise WalletError("اعتبار این کد هدیه تمام شده است.")
        amount = card.remaining
        card.spent_amount = F("spent_amount") + amount
        card.save(update_fields=["spent_amount"])

        wallet = get_wallet(user)
        Wallet.objects.filter(pk=wallet.pk).update(balance=F("balance") + amount)
        wallet.refresh_from_db()

        GiftCardRedemption.objects.create(gift_card=card, user=user, amount=amount)
        WalletTransaction.objects.create(
            wallet=wallet, kind=WalletTransaction.Kind.GIFT_CARD,
            amount=amount, gift_card=card,
        )
    return {"amount": amount, "balance": wallet.balance}


def charge_from_order_refund(*, user, order, amount: int) -> None:
    wallet = get_wallet(user)
    with transaction.atomic():
        Wallet.objects.filter(pk=wallet.pk).update(balance=F("balance") + amount)
        WalletTransaction.objects.create(
            wallet=wallet, kind=WalletTransaction.Kind.ORDER_REFUND,
            amount=amount, order=order,
        )


def debit_for_order(*, user, order, amount: int) -> None:
    """Debit wallet for an order; raise if insufficient."""
    wallet = get_wallet(user)
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
        if wallet.balance < amount:
            raise WalletError("موجودی کیف پول کافی نیست.")
        Wallet.objects.filter(pk=wallet.pk).update(balance=F("balance") - amount)
        WalletTransaction.objects.create(
            wallet=wallet, kind=WalletTransaction.Kind.ORDER_PAYMENT,
            amount=-amount, order=order,
        )
