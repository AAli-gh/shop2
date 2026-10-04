from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class SalesRep(models.Model):
    """A company sales rep (ویزیتور): visits shops and places their orders in the rep panel at /rep/.

    Made by the admin from an existing account; the account then sees «پنل ویزیتور» in the header.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, related_name="sales_rep", on_delete=models.CASCADE, verbose_name=_("user"),
    )
    code = models.CharField(_("rep code"), max_length=20, unique=True, help_text="کد پرسنلی یا شناسه کوتاه ویزیتور")
    region = models.CharField(_("region"), max_length=120, blank=True, help_text="منطقه یا مسیر پخش؛ مثلاً تهران — غرب")
    phone = models.CharField(_("phone number"), max_length=15, blank=True)
    is_active = models.BooleanField(
        _("active"), default=True, help_text="ویزیتور غیرفعال دیگر به پنل دسترسی ندارد؛ سفارش‌های قبلی‌اش می‌ماند.",
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("sales rep")
        verbose_name_plural = _("sales reps")
        ordering = ["code"]

    def __str__(self):
        return f"{self.user.name or self.user} ({self.code})"


class RepCustomer(models.Model):
    """A shop a rep sells to. Each rep sees and orders only for their own customers."""

    rep = models.ForeignKey(SalesRep, related_name="customers", on_delete=models.PROTECT, verbose_name=_("sales rep"))
    shop_name = models.CharField(_("shop name"), max_length=150)
    owner_name = models.CharField(_("owner name"), max_length=120, blank=True)
    phone = models.CharField(_("phone number"), max_length=15)
    province = models.CharField(_("province"), max_length=60)
    city = models.CharField(_("city"), max_length=60)
    address = models.CharField(_("address"), max_length=300)
    postal_code = models.CharField(_("postal code"), max_length=10, blank=True)
    notes = models.CharField(_("notes"), max_length=300, blank=True, help_text="مثلاً ساعت کاری یا روز ویزیت")
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("rep customer")
        verbose_name_plural = _("rep customers")
        ordering = ["shop_name"]

    def __str__(self):
        return f"{self.shop_name} — {self.city}"
