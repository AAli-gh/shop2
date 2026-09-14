from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


class Coupon(models.Model):
    class Kind(models.TextChoices):
        PERCENT = "percent", _("percentage")
        FIXED = "fixed", _("fixed amount")

    code = models.CharField(_("code"), max_length=40, unique=True)
    kind = models.CharField(_("type"), max_length=10, choices=Kind.choices, default=Kind.PERCENT)
    value = models.BigIntegerField(_("value"))
    max_discount_amount = models.BigIntegerField(
        _("max discount cap"), null=True, blank=True,
        help_text=_("cap for percent coupons, in Toman"),
    )
    min_order_amount = models.BigIntegerField(_("min order amount"), default=0, help_text=_("in Toman"))
    valid_from = models.DateTimeField(_("valid from"))
    valid_to = models.DateTimeField(_("valid to"))
    usage_limit = models.PositiveIntegerField(_("usage limit"), null=True, blank=True)
    used_count = models.PositiveIntegerField(_("used count"), default=0)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("coupon")
        verbose_name_plural = _("coupons")
        constraints = [
            models.CheckConstraint(
                condition=Q(kind="percent", value__lte=100) | Q(kind="fixed"),
                name="coupon_percent_value_max_100",
            ),
        ]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = self.code.upper().strip()
        super().save(*args, **kwargs)
