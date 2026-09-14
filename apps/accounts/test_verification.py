import pytest
from django.core import mail

from apps.accounts import services
from apps.accounts.models import EmailVerificationToken, User


@pytest.fixture
def pending_user(db):
    return services.register_user(email="verify@example.com", password="Pass12345!", name="کاربر")


def test_registration_creates_inactive_user_and_token(pending_user):
    assert pending_user.is_active is False
    assert pending_user.email_verified is False
    assert EmailVerificationToken.objects.filter(user=pending_user).exists()
    assert len(mail.outbox) == 1
    assert "verify/" in mail.outbox[0].body


def test_verify_token_activates(pending_user):
    token = EmailVerificationToken.objects.get(user=pending_user)
    assert services.verify_token(token.token) is True
    pending_user.refresh_from_db()
    assert pending_user.is_active and pending_user.email_verified
    assert not EmailVerificationToken.objects.filter(user=pending_user).exists()


def test_verify_bad_token_fails(db):
    assert services.verify_token("bad-token") is False


def test_expired_token_rejected(pending_user):
    from datetime import timedelta
    from django.utils import timezone

    token = EmailVerificationToken.objects.get(user=pending_user)
    token.created_at = timezone.now() - timedelta(days=4)
    token.save()
    assert services.verify_token(token.token) is False
    pending_user.refresh_from_db()
    assert pending_user.is_active is False


def test_resend_creates_fresh_token_for_expired(pending_user):
    from datetime import timedelta
    from django.utils import timezone

    token = EmailVerificationToken.objects.get(user=pending_user)
    token.created_at = timezone.now() - timedelta(days=4)
    token.save()
    services.send_verification_email(pending_user)
    new_token = EmailVerificationToken.objects.get(user=pending_user)
    assert new_token.pk != token.pk
