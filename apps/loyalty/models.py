import secrets

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

# no 0/O, 1/I/L: codes are read out and typed by hand
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 7


def new_referral_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


class LoyaltyAccount(models.Model):
    """A customer's club membership: point balance, own referral code and who referred them."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, related_name="loyalty", on_delete=models.CASCADE, verbose_name=_("user"),
    )
    # may go below zero when a return takes back points that were already spent
    points = models.IntegerField(_("points"), default=0)
    referral_code = models.CharField(_("referral code"), max_length=12, unique=True)
    referred_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="referrals", null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name=_("referred by"),
    )
    referral_rewarded = models.BooleanField(
        _("referral rewarded"), default=False,
        help_text="پاداش معرفی برای اولین خرید این مشتری پرداخت شده است.",
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("club member")
        verbose_name_plural = _("club members")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} ({self.points})"


class PointTransaction(models.Model):
    class Kind(models.TextChoices):
        PURCHASE = "purchase", _("purchase")
        RETURN = "return", _("returned goods")
        REDEEM = "redeem", _("converted to wallet credit")
        REFERRAL = "referral", _("friend referral")
        WELCOME = "welcome", _("referred customer gift")
        ADJUST = "adjust", _("manual adjustment")

    account = models.ForeignKey(
        LoyaltyAccount, related_name="transactions", on_delete=models.CASCADE, verbose_name=_("club member"),
    )
    kind = models.CharField(_("kind"), max_length=10, choices=Kind.choices)
    points = models.IntegerField(_("points"), help_text=_("positive = credit, negative = debit"))
    order = models.ForeignKey(
        "orders.Order", null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_("order"),
    )
    note = models.CharField(_("note"), max_length=200, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("point transaction")
        verbose_name_plural = _("point transactions")
        ordering = ["-created_at", "-pk"]
        constraints = [
            # an order earns its purchase points (and pays a referral) once, whatever retries happen
            models.UniqueConstraint(
                fields=["account", "order", "kind"],
                condition=models.Q(kind__in=["purchase", "referral", "welcome"]),
                name="loyalty_once_per_order",
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.points}"
