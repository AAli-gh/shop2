from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class GiftCard(models.Model):
    code = models.CharField(_("code"), max_length=40, unique=True)
    amount = models.BigIntegerField(_("amount"), help_text=_("in Toman"))
    spent_amount = models.BigIntegerField(_("spent amount"), default=0)
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("gift card")
        verbose_name_plural = _("gift cards")

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        if not self.code:
            import uuid

            self.code = f"GIFT-{uuid.uuid4().hex[:10].upper()}"
        self.code = self.code.upper().strip()
        super().save(*args, **kwargs)

    @property
    def remaining(self):
        return max(self.amount - self.spent_amount, 0)

    @property
    def is_usable(self):
        return self.is_active and self.remaining > 0


class Wallet(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, related_name="wallet", on_delete=models.CASCADE,
        verbose_name=_("user"),
    )
    balance = models.BigIntegerField(_("balance"), default=0, help_text=_("in Toman"))

    class Meta:
        verbose_name = _("wallet")
        verbose_name_plural = _("wallets")

    def __str__(self):
        return f"Wallet<{self.user.email}>: {self.balance}"


class WalletTransaction(models.Model):
    class Kind(models.TextChoices):
        GIFT_CARD = "gift_card", _("gift card charge")
        ORDER_PAYMENT = "order_payment", _("order payment")
        ORDER_REFUND = "order_refund", _("order refund")
        ADMIN_ADJUST = "admin_adjust", _("admin adjust")

    wallet = models.ForeignKey(
        Wallet, related_name="transactions", on_delete=models.CASCADE, verbose_name=_("wallet"),
    )
    kind = models.CharField(_("kind"), max_length=20, choices=Kind.choices)
    amount = models.BigIntegerField(_("amount"), help_text=_("positive = credit, negative = debit"))
    order = models.ForeignKey(
        "orders.Order", null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_("order"),
    )
    gift_card = models.ForeignKey(
        GiftCard, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_("gift card"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("wallet transaction")
        verbose_name_plural = _("wallet transactions")
        ordering = ["-created_at"]


class GiftCardRedemption(models.Model):
    """Records that a user redeemed a gift card into their wallet."""
    gift_card = models.ForeignKey(
        GiftCard, related_name="redemptions", on_delete=models.CASCADE, verbose_name=_("gift card"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="gift_redemptions", on_delete=models.CASCADE,
        verbose_name=_("user"),
    )
    amount = models.BigIntegerField(_("amount"))
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("gift card redemption")
        verbose_name_plural = _("gift card redemptions")
        constraints = [
            models.UniqueConstraint(fields=["gift_card", "user"], name="unique_gift_redemption_per_user"),
        ]
