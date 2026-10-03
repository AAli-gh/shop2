from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class WinBackMessage(models.Model):
    """One win-back offer sent to a customer who stopped buying, and the personal code it carried."""

    class Channel(models.TextChoices):
        SMS = "sms", _("SMS")
        EMAIL = "email", _("email")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="winback_messages", on_delete=models.CASCADE, verbose_name=_("user"),
    )
    coupon = models.ForeignKey(
        "discounts.Coupon", null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_("coupon"),
    )
    channel = models.CharField(_("channel"), max_length=10, choices=Channel.choices)
    # the purchase this offer follows up; a customer gets one offer per quiet spell
    last_purchase_at = models.DateTimeField(_("last purchase"))
    sent_at = models.DateTimeField(_("sent at"), default=timezone.now, db_index=True)

    class Meta:
        verbose_name = _("win-back message")
        verbose_name_plural = _("win-back messages")
        ordering = ["-sent_at"]

    def __str__(self):
        return f"{self.user} — {self.sent_at:%Y-%m-%d}"
