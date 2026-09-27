import pytest
from django.urls import reverse

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product
from apps.common.models import SiteSettings
from apps.loyalty import services
from apps.loyalty.models import LoyaltyAccount, PointTransaction
from apps.orders.models import Order, ReturnRequest
from apps.orders.services import place_order, transition_status
from apps.wallet.models import Wallet

ADDRESS = {
    "full_name": "a", "phone": "09120000000", "province": "پ",
    "city": "ش", "postal_code": "1234567890", "address_line": "addr",
}


@pytest.fixture(autouse=True)
def club(db):
    # explicit numbers so the tests don't depend on the defaults
    s = SiteSettings.load()
    s.loyalty_enabled = True
    s.loyalty_toman_per_point = 10_000
    s.loyalty_point_value = 100
    s.loyalty_min_redeem_points = 500
    s.referral_referrer_points = 2_000
    s.referral_friend_points = 1_000
    s.referral_min_order_amount = 1_000_000
    s.save()
    return s


@pytest.fixture
def product(db):
    cat = Category.objects.create(name="c", slug="c")
    return Product.objects.create(category=cat, name="p", slug="p", price=2_000_000, stock=20)


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(phone="09121110000", phone_verified=True)


def buy(user, product, quantity=1, status=None):
    cart, _ = Cart.objects.get_or_create(user=user)
    CartItem.objects.create(cart=cart, product=product, quantity=quantity)
    order = place_order(user=user, cart=cart, address_data=ADDRESS)
    Order.objects.filter(pk=order.pk).update(status=Order.Status.PAID)
    order.refresh_from_db()
    if status == "delivered":
        for step in (Order.Status.PROCESSING, Order.Status.SHIPPED, Order.Status.DELIVERED):
            order = transition_status(order=order, new_status=step)
    return order


def points(user):
    return LoyaltyAccount.objects.get(user=user).points


# ---------------------------------------------------------------- earning

def test_points_arrive_only_when_the_order_is_delivered(user, product):
    order = buy(user, product)
    assert not PointTransaction.objects.exists()

    for step in (Order.Status.PROCESSING, Order.Status.SHIPPED, Order.Status.DELIVERED):
        order = transition_status(order=order, new_status=step)
    assert points(user) == 200  # 2,000,000 Toman of goods / 10,000; shipping not counted


def test_delivery_earns_once(user, product):
    order = buy(user, product, status="delivered")
    services.order_delivered(order)  # e.g. a retried job
    assert points(user) == 200
    assert PointTransaction.objects.filter(kind=PointTransaction.Kind.PURCHASE).count() == 1


def test_disabled_club_gives_nothing(user, product, club):
    club.loyalty_enabled = False
    club.save()
    buy(user, product, status="delivered")
    assert not PointTransaction.objects.exists()


def test_completed_return_takes_back_the_refunded_points(user, product):
    from apps.orders.returns import complete_return, create_return_request

    order = buy(user, product, quantity=2, status="delivered")
    assert points(user) == 400
    item = order.items.get()
    request = create_return_request(order=order, quantities={item.pk: 1}, reason="defective",
                                    resolution="refund", description="خراب بود")
    ReturnRequest.objects.filter(pk=request.pk).update(status=ReturnRequest.Status.RECEIVED)
    complete_return(return_request=request, refund_to_wallet=True, restock=True)

    assert points(user) == 200


# ---------------------------------------------------------------- redeeming

def test_points_turn_into_wallet_credit(user, product):
    buy(user, product, quantity=3, status="delivered")  # 600 points
    amount = services.redeem(user=user, points=500)
    assert amount == 50_000
    assert points(user) == 100
    assert Wallet.objects.get(user=user).balance == 50_000


@pytest.mark.parametrize("wanted, message", [(100, "دست‌کم"), (5_000, "کافی نیست")])
def test_redeem_needs_the_minimum_and_the_balance(user, product, wanted, message):
    buy(user, product, quantity=3, status="delivered")
    with pytest.raises(services.LoyaltyError, match=message):
        services.redeem(user=user, points=wanted)
    assert points(user) == 600


def test_club_page_redeem_form(client, user, product):
    buy(user, product, quantity=3, status="delivered")
    client.force_login(user)
    page = client.get(reverse("loyalty:club"))
    assert page.status_code == 200
    client.post(reverse("loyalty:redeem"), {"points": "600"})
    assert Wallet.objects.get(user=user).balance == 60_000


# ---------------------------------------------------------------- referrals

def test_referral_link_signs_up_the_friend_under_the_referrer(client, django_user_model, _sms_outbox):
    referrer = django_user_model.objects.create_user(phone="09125550000", phone_verified=True)
    code = services.get_account(referrer).referral_code

    client.get(f"/?ref={code.lower()}")
    client.post(reverse("accounts:login"), {"phone": "09127770000"})
    client.post(reverse("accounts:login_verify"), {"code": _sms_outbox[-1]["code"]})

    friend = django_user_model.objects.get(phone="09127770000")
    assert LoyaltyAccount.objects.get(user=friend).referred_by == referrer


def test_referral_pays_both_once_on_the_first_qualifying_delivery(user, product, django_user_model):
    referrer = django_user_model.objects.create_user(phone="09125550000", phone_verified=True)
    services.set_referrer(user=user, code=services.get_account(referrer).referral_code)

    buy(user, product, status="delivered")
    buy(user, product, status="delivered")

    assert points(referrer) == 2_000
    assert points(user) == 200 + 200 + 1_000


def test_small_first_order_does_not_pay_the_referral_yet(user, product, django_user_model):
    referrer = django_user_model.objects.create_user(phone="09125550000", phone_verified=True)
    services.set_referrer(user=user, code=services.get_account(referrer).referral_code)
    cheap = Product.objects.create(category=product.category, name="q", slug="q", price=300_000, stock=5)

    buy(user, cheap, status="delivered")
    assert points(referrer) == 0
    buy(user, product, status="delivered")
    assert points(referrer) == 2_000


def test_referral_code_rules(user, product, django_user_model):
    other = django_user_model.objects.create_user(phone="09125550000", phone_verified=True)
    own = services.get_account(user).referral_code

    with pytest.raises(services.LoyaltyError, match="خودتان"):
        services.set_referrer(user=user, code=own)
    with pytest.raises(services.LoyaltyError, match="پیدا نشد"):
        services.set_referrer(user=user, code="NOPE123")

    services.set_referrer(user=other, code=own)  # user referred other...
    with pytest.raises(services.LoyaltyError):  # ...so other can't refer user back
        services.set_referrer(user=user, code=services.get_account(other).referral_code)


def test_referral_code_only_before_the_first_order(user, product, django_user_model):
    referrer = django_user_model.objects.create_user(phone="09125550000", phone_verified=True)
    buy(user, product)
    with pytest.raises(services.LoyaltyError, match="پیش از اولین خرید"):
        services.set_referrer(user=user, code=services.get_account(referrer).referral_code)


def test_manual_adjustment_in_admin_moves_the_balance(admin_client, user):
    account = services.get_account(user)
    admin_client.post("/admin/loyalty/pointtransaction/add/", {"account": account.pk, "points": "150", "note": "جبران تأخیر"})
    account.refresh_from_db()
    assert account.points == 150
    assert account.transactions.get().kind == PointTransaction.Kind.ADJUST
