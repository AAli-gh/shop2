from datetime import timedelta

import pytest
from django.utils import timezone

from apps.common.models import SiteSettings
from apps.crm import segments, winback
from apps.crm.models import WinBackMessage
from apps.discounts.models import Coupon
from apps.discounts.services import validate_coupon
from apps.orders.models import Order

NOW = timezone.now()


@pytest.fixture(autouse=True)
def campaign(db):
    s = SiteSettings.load()
    s.winback_enabled = True
    s.winback_after_days = 120
    s.winback_percent = 15
    s.winback_max_discount = 500_000
    s.winback_valid_days = 10
    s.save()
    return s


def customer(django_user_model, phone="09121110000", **extra):
    return django_user_model.objects.create_user(phone=phone, phone_verified=True, **extra)


def order(user, days_ago, status=Order.Status.DELIVERED, total=1_000_000):
    o = Order.objects.create(
        order_number=f"SH-{Order.objects.count() + 1:08d}", user=user, status=status,
        items_subtotal=total, total=total,
    )
    Order.objects.filter(pk=o.pk).update(created_at=NOW - timedelta(days=days_ago))
    return o


# ---------------------------------------------------------------- segments

@pytest.mark.parametrize("orders, days, expected", [
    (5, 10, segments.LOYAL),
    (1, 10, segments.ACTIVE),
    (1, 90, segments.AT_RISK),
    (5, 200, segments.DORMANT),
])
def test_segment_rules(orders, days, expected):
    found = segments.segment_for(orders=orders, last_purchase=NOW - timedelta(days=days), now=NOW, dormant_days=120)
    assert found == expected


def test_segments_report(django_user_model):
    loyal = customer(django_user_model, "09121110001")
    for _ in range(3):
        order(loyal, 5)
    sleeper = customer(django_user_model, "09121110002")
    order(sleeper, 300, total=7_000_000)
    order(sleeper, 400, status=Order.Status.CANCELLED)  # never counts
    customer(django_user_model, "09121110003")  # signed up, never bought

    report = segments.segments_report(segment="dormant", now=NOW)
    counts = {row["segment"].key: row["customers"] for row in report["summary"]}
    assert counts == {"loyal": 1, "active": 0, "at_risk": 0, "dormant": 1}
    assert [c["user"] for c in report["customers"]] == [sleeper]
    assert report["customers"][0]["spent"] == 7_000_000
    assert report["never_bought"] == 1


# ---------------------------------------------------------------- who gets an offer

def test_only_quiet_customers_who_can_be_reached_are_due(django_user_model):
    due = customer(django_user_model, "09121110001")
    order(due, 150)
    recent = customer(django_user_model, "09121110002")
    order(recent, 150)
    order(recent, 20, status=Order.Status.PENDING_PAYMENT)  # ordering again right now
    opted_out = customer(django_user_model, "09121110003", accepts_marketing=False)
    order(opted_out, 150)
    staff = customer(django_user_model, "09121110004", is_staff=True)
    order(staff, 150)
    no_contact = django_user_model.objects.create_user(phone="09121110005", phone_verified=False)
    order(no_contact, 150)
    never_paid = customer(django_user_model, "09121110006")
    order(never_paid, 150, status=Order.Status.CANCELLED)

    assert list(winback.candidates(NOW)) == [due]


def test_offer_is_a_personal_one_use_code_by_sms(django_user_model, _sms_outbox):
    user = customer(django_user_model)
    order(user, 150)

    assert winback.send_winback(now=NOW) == 1
    message = WinBackMessage.objects.get()
    coupon = message.coupon
    assert message.channel == "sms" and coupon.owner == user
    assert coupon.value == 15 and coupon.max_discount_amount == 500_000
    assert coupon.usage_limit == 1 and coupon.per_user_limit == 1
    assert coupon.valid_to.date() == (NOW + timedelta(days=10)).date()
    assert _sms_outbox[-1]["phone"] == user.phone
    assert coupon.code in _sms_outbox[-1]["text"]

    # nothing more for the same quiet spell…
    assert winback.send_winback(now=NOW + timedelta(days=1)) == 0
    # …but a new offer after the next purchase goes quiet too
    order(user, -1)
    assert winback.send_winback(now=NOW + timedelta(days=130)) == 1


def test_only_the_owner_can_use_the_code(django_user_model):
    user = customer(django_user_model)
    other = customer(django_user_model, "09121119999")
    order(user, 150)
    winback.send_winback(now=NOW)
    code = Coupon.objects.get().code

    assert validate_coupon(code=code, subtotal=1_000_000, user=other).error == "not_yours"
    assert validate_coupon(code=code, subtotal=1_000_000, user=user).error is None


def test_email_when_there_is_no_verified_mobile(django_user_model, mailoutbox):
    user = django_user_model.objects.create_user(email="old@example.com", password="x", email_verified=True)
    order(user, 150)
    assert winback.send_winback(now=NOW) == 1
    assert WinBackMessage.objects.get().channel == "email"
    assert Coupon.objects.get().code in mailoutbox[0].body


def test_failed_sms_leaves_no_code_behind(django_user_model, monkeypatch):
    user = customer(django_user_model)
    order(user, 150)
    monkeypatch.setattr("apps.common.sms.notify", lambda *a, **k: False)
    assert winback.send_winback(now=NOW) == 0
    assert not Coupon.objects.exists() and not WinBackMessage.objects.exists()


def test_switched_off_campaign_sends_nothing(django_user_model, campaign):
    campaign.winback_enabled = False
    campaign.save()
    order(customer(django_user_model), 150)
    assert winback.send_winback(now=NOW) == 0


def test_campaign_stats_count_returns(django_user_model):
    user = customer(django_user_model)
    order(user, 150)
    winback.send_winback(now=timezone.now() - timedelta(days=2))
    comeback = order(user, 1, total=3_000_000)
    Order.objects.filter(pk=comeback.pk).update(coupon=Coupon.objects.get())

    stats = winback.campaign_stats()
    assert stats["sent"] == 1 and stats["returned"] == 1 and stats["return_rate"] == 100
    assert stats["codes_used"] == 1 and stats["revenue"] == 3_000_000


def test_profile_opt_out(client, django_user_model):
    user = customer(django_user_model)
    client.force_login(user)
    client.post("/accounts/profile/", {"name": "سارا"})  # checkbox left unticked
    user.refresh_from_db()
    assert user.accepts_marketing is False


def test_customers_page_needs_user_permission(client, admin_client, django_user_model):
    assert admin_client.get("/dashboard/customers/?segment=dormant").status_code == 200
    clerk = django_user_model.objects.create_user(email="clerk@example.com", password="x", is_staff=True)
    client.force_login(clerk)
    assert client.get("/dashboard/customers/").status_code == 403


def test_command_dry_run(django_user_model, capsys):
    from django.core.management import call_command

    order(customer(django_user_model), 150)
    call_command("send_winback", "--dry-run")
    assert "1 customer(s)" in capsys.readouterr().out
    assert not WinBackMessage.objects.exists()
