import secrets

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Subscriber(models.Model):
    email = models.EmailField(_("email"), unique=True)
    name = models.CharField(_("name"), max_length=120, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        related_name="newsletter_subscription", on_delete=models.SET_NULL,
        verbose_name=_("user"),
    )
    is_verified = models.BooleanField(_("verified"), default=False)
    verify_token = models.CharField(_("verify token"), max_length=64, blank=True)
    unsub_token = models.CharField(_("unsubscribe token"), max_length=64, unique=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("newsletter subscriber")
        verbose_name_plural = _("newsletter subscribers")
        ordering = ["-created_at"]

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        if not self.unsub_token:
            self.unsub_token = secrets.token_urlsafe(24)
        if not self.verify_token and not self.is_verified:
            self.verify_token = secrets.token_urlsafe(24)
        super().save(*args, **kwargs)


class Campaign(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("draft")
        SENT = "sent", _("sent")

    subject = models.CharField(_("subject"), max_length=200)
    body = models.TextField(_("body"), help_text=_("blank line = new paragraph"))
    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True,
    )
    sent_count = models.PositiveIntegerField(_("sent count"), default=0)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    sent_at = models.DateTimeField(_("sent at"), null=True, blank=True)

    class Meta:
        verbose_name = _("newsletter campaign")
        verbose_name_plural = _("newsletter campaigns")
        ordering = ["-created_at"]

    def __str__(self):
        return self.subject

    def paragraphs(self):
        return [p.strip() for p in self.body.split("\n\n") if p.strip()]
