from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts import otp
from apps.accounts.models import PhoneOTP, User
from apps.cart.models import Cart
from apps.catalog.models import Category, Product
from apps.common.sms import LocmemSmsBackend, SmsError

LOGIN = PhoneOTP.Purpose.LOGIN
PHONE = "09121234567"


def last_code():
    return LocmemSmsBackend.outbox[-1]["code"]


@pytest.fixture
def no_cooldown(settings):
    settings.OTP_RESEND_SECONDS = 0


# ---------------------------------------------------------------- service

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("09121234567", PHONE), ("۰۹۱۲۱۲۳۴۵۶۷", PHONE), ("+989121234567", PHONE),
        ("00989121234567", PHONE), ("9121234567", PHONE), ("0912 123-4567", PHONE),
        ("02112345678", None), ("0912123456", None), ("abc", None), ("", None),
    ],
)
def test_normalize_phone(raw, expected):
    assert otp.normalize_phone(raw) == expected


@pytest.mark.django_db
def test_first_login_creates_a_verified_account_without_email(no_cooldown):
    otp.request_code(phone=PHONE, purpose=LOGIN)
    user, created = otp.login_with_code(phone=PHONE, code=last_code())
    assert created
    assert user.email is None and user.phone == PHONE and user.phone_verified
    assert not user.has_usable_password()

    otp.request_code(phone=PHONE, purpose=LOGIN)
    again, created_again = otp.login_with_code(phone=PHONE, code=last_code())
    assert (again.pk, created_again) == (user.pk, False)


@pytest.mark.django_db
def test_code_is_hashed_and_single_use():
    otp.request_code(phone=PHONE, purpose=LOGIN)
    code = last_code()
    assert code not in PhoneOTP.objects.get().code_hash
    otp.login_with_code(phone=PHONE, code=code)
    with pytest.raises(otp.OtpError):
        otp.login_with_code(phone=PHONE, code=code)


@pytest.mark.django_db
def test_wrong_codes_are_counted_and_lock_the_code(settings):
    settings.OTP_MAX_ATTEMPTS = 3
    otp.request_code(phone=PHONE, purpose=LOGIN)
    code = last_code()
    wrong = "00000" if code != "00000" else "11111"
    for _ in range(2):
        with pytest.raises(otp.OtpError):
            otp.login_with_code(phone=PHONE, code=wrong)
    assert PhoneOTP.objects.get().attempts == 2  # persisted even though an error was raised
    with pytest.raises(otp.OtpError):
        otp.login_with_code(phone=PHONE, code=wrong)
    with pytest.raises(otp.OtpError):  # locked: even the right code no longer works
        otp.login_with_code(phone=PHONE, code=code)


@pytest.mark.django_db
def test_expired_code_is_rejected():
    otp.request_code(phone=PHONE, purpose=LOGIN)
    PhoneOTP.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    with pytest.raises(otp.OtpError):
        otp.login_with_code(phone=PHONE, code=last_code())


@pytest.mark.django_db
def test_resend_cooldown_and_only_the_newest_code_works(settings):
    settings.OTP_RESEND_SECONDS = 60
    otp.request_code(phone=PHONE, purpose=LOGIN)
    old_code = last_code()
    with pytest.raises(otp.OtpError):
        otp.request_code(phone=PHONE, purpose=LOGIN)

    PhoneOTP.objects.update(created_at=timezone.now() - timedelta(seconds=61))
    otp.request_code(phone=PHONE, purpose=LOGIN)
    new_code = last_code()
    if old_code != new_code:
        with pytest.raises(otp.OtpError):
            otp.check_code(phone=PHONE, code=old_code, purpose=LOGIN)
    otp.check_code(phone=PHONE, code=new_code, purpose=LOGIN)


@pytest.mark.django_db
def test_failed_sms_leaves_no_code_and_no_cooldown(monkeypatch, settings):
    settings.OTP_RESEND_SECONDS = 60

    def broken(self, phone, code):
        raise SmsError("provider down")

    monkeypatch.setattr(LocmemSmsBackend, "send_otp", broken)
    with pytest.raises(otp.OtpError):
        otp.request_code(phone=PHONE, purpose=LOGIN)
    assert not PhoneOTP.objects.exists()
    assert otp.seconds_until_resend(PHONE, LOGIN) == 0


@pytest.mark.django_db
def test_unverified_profile_number_does_not_unlock_that_account(django_user_model):
    # someone typed this number into their profile without proving they own it
    squatter = django_user_model.objects.create_user(email="squat@example.com", password="x", phone=PHONE)
    otp.request_code(phone=PHONE, purpose=LOGIN)
    user, created = otp.login_with_code(phone=PHONE, code=last_code())
    assert created and user.pk != squatter.pk
    squatter.refresh_from_db()
    assert squatter.phone is None


@pytest.mark.django_db
def test_disabled_account_cannot_sign_in_by_phone(django_user_model):
    django_user_model.objects.create_user(phone=PHONE, phone_verified=True, is_active=False)
    otp.request_code(phone=PHONE, purpose=LOGIN)
    with pytest.raises(otp.OtpError):
        otp.login_with_code(phone=PHONE, code=last_code())


# ---------------------------------------------------------------- views

@pytest.mark.django_db
def test_phone_login_flow_signs_in_and_honours_next(client, django_user_model):
    existing = django_user_model.objects.create_user(phone=PHONE, phone_verified=True)
    resp = client.post("/accounts/login/", {"phone": "۰۹۱۲۱۲۳۴۵۶۷", "next": "/cart/"})
    assert resp.status_code == 302 and resp.url == "/accounts/login/verify/"
    assert "۰۹۱۲۱۲۳۴۵۶۷" in client.get(resp.url).content.decode()

    resp = client.post("/accounts/login/verify/", {"code": last_code()})
    assert resp.url == "/cart/"
    assert int(client.session["_auth_user_id"]) == existing.pk


@pytest.mark.django_db
def test_new_phone_account_lands_on_profile_and_ignores_external_next(client):
    client.post("/accounts/login/", {"phone": PHONE, "next": "https://evil.example/"})
    resp = client.post("/accounts/login/verify/", {"code": last_code()})
    assert resp.url == "/accounts/profile/"
    assert User.objects.filter(phone=PHONE, email__isnull=True).exists()


@pytest.mark.django_db
def test_wrong_code_shows_error_and_stays_signed_out(client):
    client.post("/accounts/login/", {"phone": PHONE})
    code = last_code()
    resp = client.post("/accounts/login/verify/", {"code": "00000" if code != "00000" else "11111"})
    assert resp.status_code == 200
    assert "کد واردشده درست نیست" in resp.content.decode()
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_verify_page_without_a_requested_code_goes_back(client):
    resp = client.get("/accounts/login/verify/")
    assert resp.url == "/accounts/login/"


@pytest.mark.django_db
def test_invalid_number_sends_nothing(client):
    resp = client.post("/accounts/login/", {"phone": "12345"})
    assert resp.status_code == 200
    assert "شماره موبایل معتبر نیست" in resp.content.decode()
    assert LocmemSmsBackend.outbox == []


@pytest.mark.django_db
def test_resubmitting_the_same_number_reuses_the_code(client, settings):
    settings.OTP_RESEND_SECONDS = 60
    client.post("/accounts/login/", {"phone": PHONE})
    resp = client.post("/accounts/login/", {"phone": PHONE})
    assert resp.url == "/accounts/login/verify/"
    assert len(LocmemSmsBackend.outbox) == 1


@pytest.mark.django_db
def test_codes_per_number_are_capped_across_ips(client, no_cooldown):
    for i in range(3):
        resp = client.post("/accounts/login/resend/" if i else "/accounts/login/", {"phone": PHONE}, REMOTE_ADDR=f"10.9.0.{i}")
    assert len(LocmemSmsBackend.outbox) == 3
    resp = client.post("/accounts/login/resend/", REMOTE_ADDR="10.9.0.50", follow=True)
    assert "کد زیادی درخواست شده" in resp.content.decode()
    assert len(LocmemSmsBackend.outbox) == 3


@pytest.mark.django_db
def test_guest_cart_is_kept_after_phone_login(client):
    cat = Category.objects.create(name="c", slug="c")
    product = Product.objects.create(category=cat, name="p", slug="p", price=100_000, stock=5)
    client.post(f"/cart/htmx/add/{product.pk}/")
    client.post("/accounts/login/", {"phone": PHONE})
    client.post("/accounts/login/verify/", {"code": last_code()})
    cart = Cart.objects.get(user__phone=PHONE)
    assert cart.items.filter(product=product).exists()


@pytest.mark.django_db
def test_profile_can_no_longer_set_an_unverified_phone(client, django_user_model):
    user = django_user_model.objects.create_user(email="p@example.com", password="x")
    client.force_login(user)
    client.post("/accounts/profile/", {"name": "علی", "phone": PHONE})
    user.refresh_from_db()
    assert user.name == "علی" and user.phone is None


@pytest.mark.django_db
def test_adding_a_phone_to_an_account_requires_the_code(client, django_user_model):
    user = django_user_model.objects.create_user(email="p@example.com", password="x")
    client.force_login(user)
    resp = client.post("/accounts/profile/phone/", {"phone": PHONE})
    assert resp.url == "/accounts/profile/phone/verify/"
    user.refresh_from_db()
    assert user.phone is None  # nothing changes before the code is confirmed

    resp = client.post("/accounts/profile/phone/verify/", {"code": last_code()})
    assert resp.url == "/accounts/profile/"
    user.refresh_from_db()
    assert (user.phone, user.phone_verified) == (PHONE, True)


@pytest.mark.django_db
def test_cannot_claim_a_number_verified_on_another_account(client, django_user_model):
    django_user_model.objects.create_user(phone=PHONE, phone_verified=True)
    user = django_user_model.objects.create_user(email="p@example.com", password="x")
    client.force_login(user)
    resp = client.post("/accounts/profile/phone/", {"phone": PHONE})
    assert resp.status_code == 200
    assert "به حساب دیگری متصل است" in resp.content.decode()
    assert LocmemSmsBackend.outbox == []


@pytest.mark.django_db
def test_phone_only_account_can_set_a_password(client, django_user_model):
    user = django_user_model.objects.create_user(phone=PHONE, phone_verified=True)
    client.force_login(user)
    resp = client.post("/accounts/profile/password/", {"new_password1": "Strong-pass-123", "new_password2": "Strong-pass-123"})
    assert resp.status_code == 302
    user.refresh_from_db()
    assert user.check_password("Strong-pass-123")
