from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email=None, password=None, **extra_fields):
        # phone-login accounts have no email; one of the two identities is required
        if not email and not extra_fields.get("phone"):
            raise ValueError("email or phone is required")
        email = self.normalize_email(email) if email else None
        user = self.model(email=email, **extra_fields)
        user.set_password(password)  # None -> unusable password (phone-only accounts)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("is_staff must be True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("is_superuser must be True")
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None
    email = models.EmailField(_("email address"), unique=True, null=True, blank=True)
    name = models.CharField(_("full name"), max_length=120, blank=True)
    # canonical 09xxxxxxxxx; it identifies the account for SMS login only once phone_verified
    phone = models.CharField(_("phone number"), max_length=15, unique=True, null=True, blank=True)
    phone_verified = models.BooleanField(_("phone verified"), default=False)
    email_verified = models.BooleanField(_("email verified"), default=False)
    # promotional messages such as the win-back coupon (apps.crm); order and account texts are always sent
    accepts_marketing = models.BooleanField(_("accepts offers"), default=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")

    def __str__(self):
        return self.email or self.phone or f"user-{self.pk}"


class Address(models.Model):
    user = models.ForeignKey(
        User, related_name="addresses", on_delete=models.CASCADE, verbose_name=_("user")
    )
    full_name = models.CharField(_("full name"), max_length=120)
    phone = models.CharField(_("phone number"), max_length=15)
    province = models.CharField(_("province"), max_length=60)
    city = models.CharField(_("city"), max_length=60)
    postal_code = models.CharField(_("postal code"), max_length=10)
    address_line = models.CharField(_("address"), max_length=300)
    is_default = models.BooleanField(_("default address"), default=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("address")
        verbose_name_plural = _("addresses")
        ordering = ["-is_default", "-created_at"]

    def __str__(self):
        return f"{self.city} - {self.address_line[:40]}"


class PhoneOTP(models.Model):
    """A one-time SMS code. Only a keyed hash of the code is stored."""

    class Purpose(models.TextChoices):
        LOGIN = "login", _("login")
        CHANGE_PHONE = "change", _("change phone")
        ADMIN = "admin", _("admin sign-in")

    phone = models.CharField(_("phone number"), max_length=15, db_index=True)
    purpose = models.CharField(_("purpose"), max_length=10, choices=Purpose.choices)
    code_hash = models.CharField(_("code hash"), max_length=64)
    attempts = models.PositiveSmallIntegerField(_("attempts"), default=0)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    expires_at = models.DateTimeField(_("expires at"))
    consumed_at = models.DateTimeField(_("consumed at"), null=True, blank=True)

    class Meta:
        verbose_name = _("SMS code")
        verbose_name_plural = _("SMS codes")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.phone} ({self.purpose})"


class EmailVerificationToken(models.Model):
    user = models.OneToOneField(
        User, related_name="email_verification_token", on_delete=models.CASCADE,
        verbose_name=_("user"),
    )
    token = models.CharField(_("token"), max_length=64, unique=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("email verification token")
        verbose_name_plural = _("email verification tokens")

    def save(self, *args, **kwargs):
        if not self.token:
            import secrets

            self.token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    def is_expired(self):
        from datetime import timedelta
        from django.utils import timezone

        return timezone.now() > self.created_at + timedelta(days=3)
