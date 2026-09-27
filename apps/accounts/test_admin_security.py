import pytest
from django.core.checks import run_checks

from apps.accounts.admin_site import NO_VERIFIED_PHONE, SESSION_VERIFIED
from apps.catalog.models import Category, Product

PASSWORD = "S3cure-pass-for-tests"
LOGIN_URL = "/admin/login/"


@pytest.fixture
def staff(django_user_model):
    return django_user_model.objects.create_user(
        email="manager@example.com", password=PASSWORD, is_staff=True, is_superuser=True,
        phone="09121112233", phone_verified=True,
    )


@pytest.fixture
def two_factor(settings):
    settings.ADMIN_2FA_ENABLED = True


def _password_step(client, email="manager@example.com", password=PASSWORD):
    return client.post(LOGIN_URL, {"username": email, "password": password, "next": "/admin/catalog/product/"})


@pytest.mark.django_db
def test_without_2fa_password_alone_signs_in(client, staff):
    response = _password_step(client)
    assert response.status_code == 302
    assert client.get("/admin/").status_code == 200


@pytest.mark.django_db
def test_2fa_password_step_texts_a_code_without_signing_in(client, staff, two_factor, _sms_outbox):
    response = _password_step(client)

    assert response.status_code == 302 and response["Location"] == "/admin/login/verify/"
    assert "_auth_user_id" not in client.session
    assert client.get("/admin/").status_code == 302
    assert [m["phone"] for m in _sms_outbox] == ["09121112233"]


@pytest.mark.django_db
def test_2fa_code_step_signs_in_and_keeps_next(client, staff, two_factor, _sms_outbox):
    _password_step(client)
    page = client.get("/admin/login/verify/").content.decode()
    assert "0912***2233" in page

    wrong = client.post("/admin/login/verify/", {"code": "00000" if _sms_outbox[0]["code"] != "00000" else "11111"})
    assert wrong.status_code == 200 and "کد واردشده درست نیست" in wrong.content.decode()

    response = client.post("/admin/login/verify/", {"code": _sms_outbox[0]["code"]})
    assert response.status_code == 302 and response["Location"] == "/admin/catalog/product/"
    assert client.session[SESSION_VERIFIED] == staff.pk
    assert client.get("/admin/").status_code == 200


@pytest.mark.django_db
def test_2fa_requires_a_verified_phone(client, staff, two_factor, _sms_outbox):
    staff.phone_verified = False
    staff.save()

    response = _password_step(client)

    assert response.status_code == 200
    assert NO_VERIFIED_PHONE in response.content.decode()
    assert _sms_outbox == []
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_2fa_wrong_password_sends_nothing(client, staff, two_factor, _sms_outbox):
    response = _password_step(client, password="wrong-password")
    assert response.status_code == 200
    assert _sms_outbox == []


@pytest.mark.django_db
def test_verify_page_needs_the_password_step_first(client, staff, two_factor):
    assert client.get("/admin/login/verify/")["Location"] == "/admin/login/"


@pytest.mark.django_db
def test_2fa_storefront_session_does_not_open_staff_pages(client, staff, two_factor, django_user_model):
    """A staff account signed in on the site (e.g. by phone code alone) must still pass the admin sign-in."""
    from apps.orders.test_invoice_returns import make_order

    customer = django_user_model.objects.create_user(email="customer@example.com", password="x")
    category = Category.objects.create(name="c", slug="c")
    order = make_order(customer, [Product.objects.create(category=category, name="p", slug="p", price=1000, stock=5)],
                       quantities=(1,))
    client.force_login(staff)

    for url in ("/admin/", "/admin/orders/order/", "/dashboard/", "/logs/", "/admin/catalog/product/import/"):
        response = client.get(url)
        assert response.status_code == 302 and response["Location"].startswith(LOGIN_URL), url
    assert client.get(f"/orders/{order.order_number}/invoice/").status_code == 404


@pytest.mark.django_db
def test_admin_login_is_rate_limited_per_account(client, staff, monkeypatch):
    # counters live in fixed windows; freeze the clock so the run can't straddle a window boundary
    monkeypatch.setattr("apps.common.ratelimit.time.time", lambda: 1_700_000_000.0)
    for _ in range(5):
        assert _password_step(client, password="wrong-password").status_code == 200
    assert _password_step(client, password="wrong-password").status_code == 429


@pytest.mark.django_db
def test_admin_pages_are_not_indexed_and_robots_hides_the_path(client):
    assert '<meta name="robots" content="noindex, nofollow">' in client.get(LOGIN_URL).content.decode()
    assert "admin" not in client.get("/robots.txt").content.decode()


def test_deploy_check_flags_the_default_admin_path(settings):
    settings.ADMIN_URL = "admin/"
    assert "shop.W001" in [m.id for m in run_checks(include_deployment_checks=True)]
    settings.ADMIN_URL = "panel-7fk2q/"
    assert "shop.W001" not in [m.id for m in run_checks(include_deployment_checks=True)]


@pytest.fixture
def support(django_user_model):
    from django.contrib.auth.models import Group

    from apps.common.groups import setup_groups

    setup_groups()
    user = django_user_model.objects.create_user(email="support@example.com", password=PASSWORD, is_staff=True)
    user.groups.add(Group.objects.get(name="پشتیبانی"))
    return user


def _user_form(user, **changes):
    data = {"email": user.email or "", "phone": user.phone or "", "name": user.name, "is_active": "on"}
    if user.phone_verified:
        data["phone_verified"] = "on"
    data.update(changes)
    return data


@pytest.mark.django_db
def test_support_cannot_make_itself_superuser(client, support):
    client.force_login(support)
    response = client.post(
        f"/admin/accounts/user/{support.pk}/change/",
        _user_form(support, is_superuser="on", is_staff="on"),
    )
    assert response.status_code == 302
    support.refresh_from_db()
    assert not support.is_superuser


@pytest.mark.django_db
def test_support_cannot_take_over_a_manager(client, support, staff):
    client.force_login(support)
    assert client.get(f"/admin/accounts/user/{staff.pk}/password/").status_code == 403
    response = client.post(f"/admin/accounts/user/{staff.pk}/change/", _user_form(staff, phone="09350000000"))
    assert response.status_code == 403
    staff.refresh_from_db()
    assert staff.phone == "09121112233"


@pytest.mark.django_db
def test_support_still_edits_customers(client, support, django_user_model):
    customer = django_user_model.objects.create_user(phone="09125556677", phone_verified=True)
    client.force_login(support)
    response = client.post(f"/admin/accounts/user/{customer.pk}/change/", _user_form(customer, name="سارا"))
    assert response.status_code == 302
    customer.refresh_from_db()
    assert customer.name == "سارا"
