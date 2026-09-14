from django.db import models
from django.utils.translation import gettext_lazy as _


class Payment(models.Model):
    """A payment attempt against an order, owned by a gateway provider.

    Gateways work in two steps: create (server-side request -> authority)
    then verify (server-side check after the bank redirects back to our
    callback). This record keeps the whole lifecycle so a payment is only
    ever settled once, no matter how many times a callback or page revisit
    arrives.
    """

    class Status(models.TextChoices):
        CREATED = "created", "ایجادشده"
        VERIFIED = "verified", "تأییدشده"
        FAILED = "failed", "ناموفق"

    order = models.ForeignKey(
        "orders.Order", related_name="payments", on_delete=models.CASCADE,
        verbose_name=_("order"),
    )
    provider = models.CharField(_("provider"), max_length=40)
    amount_toman = models.BigIntegerField(_("amount"), help_text=_("in Toman"))
    fee_toman = models.BigIntegerField(_("gateway fee"), null=True, blank=True, help_text=_("in Toman"))
    authority = models.CharField(_("authority"), max_length=128, blank=True)
    ref_id = models.CharField(_("reference id"), max_length=80, blank=True)
    card_pan = models.CharField(_("card pan"), max_length=40, blank=True)
    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.CREATED, db_index=True,
    )
    response = models.TextField(_("raw response"), blank=True, help_text="آخرین پاسخ سرویس درگاه")
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("payment")
        verbose_name_plural = _("payments")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.provider}:{self.order.order_number} ({self.get_status_display()})"
