"""Phone login and phone verification with one-time SMS codes."""
import hashlib
import hmac
import math
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import PhoneOTP, User
from apps.common import sms

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_MOBILE = re.compile(r"^09\d{9}$")


class OtpError(Exception):
    pass


def normalize_phone(raw: str) -> str | None:
    """Iranian mobile number in canonical 09xxxxxxxxx form, or None if it isn't one."""
    value = re.sub(r"[\s\-()]", "", (raw or "").translate(_DIGITS))
    if value.startswith("+98"):
        value = "0" + value[3:]
    elif value.startswith("0098"):
        value = "0" + value[4:]
    elif value.startswith("98") and len(value) == 12:
        value = "0" + value[2:]
    elif value.startswith("9") and len(value) == 10:
        value = "0" + value
    return value if _MOBILE.match(value) else None


def _hash(phone: str, code: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def _live_codes(phone: str, purpose: str):
    return PhoneOTP.objects.filter(
        phone=phone, purpose=purpose, consumed_at__isnull=True, expires_at__gt=timezone.now(),
    )


def has_live_code(phone: str, purpose: str) -> bool:
    return _live_codes(phone, purpose).exists()


def seconds_until_resend(phone: str, purpose: str) -> int:
    latest = PhoneOTP.objects.filter(phone=phone, purpose=purpose).order_by("-created_at").first()
    if latest is None:
        return 0
    waited = (timezone.now() - latest.created_at).total_seconds()
    return max(0, math.ceil(settings.OTP_RESEND_SECONDS - waited))


def request_code(*, phone: str, purpose: str) -> PhoneOTP:
    """Text a fresh code to phone. Earlier codes stop working; resends are throttled."""
    wait = seconds_until_resend(phone, purpose)
    if wait:
        raise OtpError(f"برای ارسال دوباره کد {wait} ثانیه صبر کنید.")

    code = "".join(secrets.choice("0123456789") for _ in range(settings.OTP_LENGTH))
    with transaction.atomic():
        _live_codes(phone, purpose).update(consumed_at=timezone.now())
        otp = PhoneOTP.objects.create(
            phone=phone, purpose=purpose, code_hash=_hash(phone, code),
            expires_at=timezone.now() + timedelta(seconds=settings.OTP_TTL_SECONDS),
        )
    try:
        sms.get_backend().send_otp(phone, code)
    except sms.SmsError as exc:
        otp.delete()  # nothing was delivered, so don't make the customer wait out a cooldown
        raise OtpError("ارسال پیامک ناموفق بود؛ چند دقیقه بعد دوباره تلاش کنید.") from exc
    return otp


def check_code(*, phone: str, code: str, purpose: str) -> None:
    """Consume the live code for phone if it matches; raise OtpError otherwise.

    The error is raised after the transaction commits so failed attempts are counted.
    """
    error = _consume_code(phone=phone, code=code, purpose=purpose)
    if error:
        raise OtpError(error)


@transaction.atomic
def _consume_code(*, phone: str, code: str, purpose: str) -> str:
    code = (code or "").strip().translate(_DIGITS)
    otp = _live_codes(phone, purpose).select_for_update().order_by("-created_at").first()
    if otp is None:
        return "کد منقضی شده است؛ کد جدید دریافت کنید."

    otp.attempts += 1
    if hmac.compare_digest(otp.code_hash, _hash(phone, code)):
        otp.consumed_at = timezone.now()
        otp.save(update_fields=["attempts", "consumed_at"])
        return ""
    if otp.attempts >= settings.OTP_MAX_ATTEMPTS:
        otp.consumed_at = timezone.now()
        otp.save(update_fields=["attempts", "consumed_at"])
        return "تعداد تلاش‌ها بیش از حد بود؛ کد جدید دریافت کنید."
    otp.save(update_fields=["attempts"])
    return "کد واردشده درست نیست."


def login_with_code(*, phone: str, code: str) -> tuple[User, bool]:
    """Verify a login code; return the phone's account (created on first login) and whether it is new."""
    check_code(phone=phone, code=code, purpose=PhoneOTP.Purpose.LOGIN)

    with transaction.atomic():
        user = User.objects.select_for_update().filter(phone=phone).first()
        if user is not None and not user.phone_verified:
            # a number typed into a profile was never proven, so it can't unlock that account
            user.phone = None
            user.save(update_fields=["phone"])
            user = None
        if user is not None and not user.is_active:
            raise OtpError("این حساب غیرفعال شده است؛ با پشتیبانی تماس بگیرید.")
        created = user is None
        if created:
            user = User.objects.create_user(phone=phone, phone_verified=True)

    if created:
        from apps.common import shoplog

        shoplog.user_registered(user)
    return user, created


def change_phone_with_code(*, user: User, phone: str, code: str) -> User:
    """Attach a code-verified number to a signed-in account."""
    check_code(phone=phone, code=code, purpose=PhoneOTP.Purpose.CHANGE_PHONE)

    with transaction.atomic():
        holder = User.objects.select_for_update().filter(phone=phone).exclude(pk=user.pk).first()
        if holder is not None:
            if holder.phone_verified:
                raise OtpError("این شماره به حساب دیگری متصل است.")
            holder.phone = None
            holder.save(update_fields=["phone"])
        user.phone = phone
        user.phone_verified = True
        user.save(update_fields=["phone", "phone_verified"])
    return user
