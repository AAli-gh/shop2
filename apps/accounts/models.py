from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
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
    email = models.EmailField(_("email address"), unique=True)
    name = models.CharField(_("full name"), max_length=120, blank=True)
    phone = models.CharField(_("phone number"), max_length=15, blank=True)
    email_verified = models.BooleanField(_("email verified"), default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")

    def __str__(self):
        return self.email


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
