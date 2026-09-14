import pytest

from apps.wallet import services
from apps.wallet.models import GiftCard, Wallet, WalletTransaction
from apps.wallet.services import WalletError


@pytest.fixture
def user(db, django_user_model):
    return django_user_model.objects.create_user(email="w@example.com", password="x")


def test_redeem_gift_card_charges_wallet(user, db):
    GiftCard.objects.create(code="GIFT-TEST123", amount=500_000)
    result = services.redeem_gift_card(user=user, code="gift-test123")
    assert result["amount"] == 500_000
    assert services.get_wallet(user).balance == 500_000
    assert WalletTransaction.objects.filter(kind=WalletTransaction.Kind.GIFT_CARD).exists()
    card = GiftCard.objects.get(code="GIFT-TEST123")
    assert card.spent_amount == 500_000


def test_redeem_twice_blocked(user, db):
    GiftCard.objects.create(code="GIFT-ONCE", amount=100_000)
    services.redeem_gift_card(user=user, code="GIFT-ONCE")
    with pytest.raises(WalletError):
        services.redeem_gift_card(user=user, code="GIFT-ONCE")


def test_redeem_unknown_code(user, db):
    with pytest.raises(WalletError):
        services.redeem_gift_card(user=user, code="NOPE")


def test_redeem_exhausted_card_by_two_users(db, django_user_model):
    u1 = django_user_model.objects.create_user(email="a@example.com", password="x")
    u2 = django_user_model.objects.create_user(email="b@example.com", password="x")
    card = GiftCard.objects.create(code="GIFT-SMALL", amount=50_000)
    services.redeem_gift_card(user=u1, code="GIFT-SMALL")
    assert card.refresh_from_db() is None
    card.refresh_from_db()
    assert card.remaining == 0
    with pytest.raises(WalletError):
        services.redeem_gift_card(user=u2, code="GIFT-SMALL")


def test_debit_for_order_insufficient(user, db):
    services.get_wallet(user)  # balance 0
    with pytest.raises(WalletError):
        services.debit_for_order(user=user, order=None, amount=10_000)


def test_debit_and_refund_roundtrip(user, db):
    GiftCard.objects.create(code="GIFT-R", amount=200_000)
    services.redeem_gift_card(user=user, code="GIFT-R")
    services.debit_for_order(user=user, order=None, amount=150_000)
    assert services.get_wallet(user).balance == 50_000
    services.charge_from_order_refund(user=user, order=None, amount=150_000)
    assert services.get_wallet(user).balance == 200_000
