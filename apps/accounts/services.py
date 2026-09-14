import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

from apps.accounts.models import Address, EmailVerificationToken

User = get_user_model()


def register_user(*, email: str, password: str, name: str = "") -> User:
    email = User.objects.normalize_email(email)
    user = User.objects.create_user(email=email, password=password, name=name, is_active=False)
    from apps.common import shoplog

    shoplog.user_registered(user)
    send_verification_email(user)
    return user


def send_verification_email(user) -> None:
    token, _ = EmailVerificationToken.objects.get_or_create(user=user)
    # refresh token if already used/expired
    if token.is_expired():
        token.delete()
        token = EmailVerificationToken.objects.create(user=user)
    link = settings.SITE_URL + reverse("accounts:verify_email", kwargs={"token": token.token})
    subject = f"تأیید ایمیل — {settings.SITE_STORE_NAME}"
    body = render_to_string(
        "accounts/emails/email_verification.txt",
        {"user": user, "link": link},
    )
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)


def verify_token(token_str: str) -> bool:
    token = EmailVerificationToken.objects.filter(token=token_str).select_related("user").first()
    if not token or token.is_expired():
        return False
    user = token.user
    user.is_active = True
    user.email_verified = True
    user.save(update_fields=["is_active", "email_verified"])
    token.delete()
    from apps.common import shoplog

    shoplog.user_verified(user)
    return True


def update_profile(*, user: User, name: str, phone: str) -> User:
    user.name = name
    user.phone = phone
    user.save(update_fields=["name", "phone"])
    return user


def set_default_address(*, user: User, address_id: int) -> None:
    user.addresses.update(is_default=False)
    user.addresses.filter(pk=address_id).update(is_default=True)


def create_address(*, user: User, **data) -> Address:
    if not user.addresses.exists():
        data["is_default"] = True
    elif data.get("is_default"):
        user.addresses.update(is_default=False)
    return Address.objects.create(user=user, **data)


def update_address(*, address: Address, **data) -> Address:
    for field, value in data.items():
        setattr(address, field, value)
    address.save()
    if address.is_default:
        address.user.addresses.exclude(pk=address.pk).update(is_default=False)
    return address


def delete_address(*, user: User, address_id: int) -> None:
    user.addresses.filter(pk=address_id).delete()
