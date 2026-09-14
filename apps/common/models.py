from django.core.cache import cache
from django.db import models
from django.utils.translation import gettext_lazy as _


class SiteSettings(models.Model):
    store_name = models.CharField(_("store name"), max_length=100, default="فروشگاه من")
    shipping_flat_rate = models.BigIntegerField(
        _("flat shipping rate"), default=50_000, help_text=_("in Toman")
    )
    free_shipping_threshold = models.BigIntegerField(
        _("free shipping threshold"), null=True, blank=True, help_text=_("in Toman")
    )
    install_fee = models.BigIntegerField(
        _("install fee"), default=0, help_text=_("هزینه نصب (تومان)؛ ۰ = رایگان")
    )
    contact_phone = models.CharField(_("contact phone"), max_length=20, blank=True)
    about_text = models.TextField(_("about text"), blank=True)

    class Meta:
        verbose_name = _("site settings")
        verbose_name_plural = _("site settings")

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete("site_settings")

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ContactMessage(models.Model):
    name = models.CharField(_("name"), max_length=120)
    email = models.EmailField(_("email"))
    subject = models.CharField(_("subject"), max_length=200)
    body = models.TextField(_("message"), max_length=5000)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    is_read = models.BooleanField(_("read"), default=False)

    class Meta:
        verbose_name = _("contact message")
        verbose_name_plural = _("contact messages")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name}: {self.subject}"


class StaticPage(models.Model):
    class PageKey(models.TextChoices):
        FAQ = "faq", _("FAQ")
        RETURN_POLICY = "return_policy", _("return policy")

    key = models.CharField(_("key"), max_length=20, choices=PageKey.choices, unique=True)
    title = models.CharField(_("title"), max_length=200)
    body = models.TextField(_("body"), help_text=_("Markdown-like plain text; blank line = new paragraph"))
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("static page")
        verbose_name_plural = _("static pages")

    def __str__(self):
        return self.title

    def paragraphs(self):
        return [p.strip() for p in self.body.split("\n\n") if p.strip()]
