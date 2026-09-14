import pytest
from django.test import override_settings
from django.urls import reverse

from apps.common.ratelimit import is_limited


def test_counter_allows_limit_then_blocks_per_identity():
    assert [is_limited("t", "a", limit=2, window=60) for _ in range(3)] == [False, False, True]
    assert is_limited("t", "b", limit=2, window=60) is False  # another client has its own counter


@override_settings(RATELIMIT_ENABLE=False)
def test_can_be_switched_off():
    assert not any(is_limited("t", "a", limit=1, window=60) for _ in range(5))


@pytest.mark.django_db
def test_login_guessing_is_capped_per_account_even_across_ips(client):
    for i in range(8):
        resp = client.post(
            "/accounts/login/", {"username": "victim@example.com", "password": f"wrong{i}"},
            REMOTE_ADDR=f"10.0.0.{i}",
        )
        assert resp.status_code == 200
    resp = client.post(
        "/accounts/login/", {"username": "victim@example.com", "password": "again"}, REMOTE_ADDR="10.0.0.99",
    )
    assert resp.status_code == 429
    assert resp["Retry-After"] == "600"
    assert "تعداد تلاش‌ها بیش از حد مجاز" in resp.content.decode()


@pytest.mark.django_db
def test_login_is_capped_per_ip(client):
    for i in range(20):
        client.post("/accounts/login/", {"username": f"u{i}@example.com", "password": "x"}, REMOTE_ADDR="10.1.1.1")
    resp = client.post("/accounts/login/", {"username": "new@example.com", "password": "x"}, REMOTE_ADDR="10.1.1.1")
    assert resp.status_code == 429


@pytest.mark.django_db
def test_login_page_itself_is_never_limited(client):
    for _ in range(30):
        assert client.get("/accounts/login/").status_code == 200


@pytest.mark.django_db
def test_register_limit_is_per_ip(client):
    for _ in range(5):
        assert client.post("/accounts/register/", {}, REMOTE_ADDR="10.2.2.2").status_code == 200
    assert client.post("/accounts/register/", {}, REMOTE_ADDR="10.2.2.2").status_code == 429
    assert client.post("/accounts/register/", {}, REMOTE_ADDR="10.2.2.3").status_code == 200


@pytest.mark.django_db
def test_htmx_requests_get_a_plain_429(client):
    url = reverse("newsletter:subscribe")
    for i in range(10):
        client.post(url, {"email": f"n{i}@example.com"}, HTTP_HX_REQUEST="true")
    resp = client.post(url, {"email": "late@example.com"}, HTTP_HX_REQUEST="true")
    assert resp.status_code == 429
    assert resp["Content-Type"].startswith("text/plain")


@pytest.mark.django_db
def test_gift_card_guessing_is_capped(client, django_user_model):
    client.force_login(django_user_model.objects.create_user(email="gift@example.com", password="x"))
    url = reverse("wallet:redeem")
    for i in range(5):
        assert client.post(url, {"code": f"GIFT-GUESS{i}"}).status_code == 302
    assert client.post(url, {"code": "GIFT-GUESS9"}).status_code == 429


@pytest.mark.django_db
@override_settings(RATELIMIT_IP_HEADER="HTTP_X_REAL_IP")
def test_proxy_header_identifies_the_client(client):
    # behind nginx every request comes from 127.0.0.1; X-Real-IP tells clients apart
    for _ in range(5):
        client.post("/accounts/register/", {}, REMOTE_ADDR="127.0.0.1", HTTP_X_REAL_IP="1.1.1.1")
    assert client.post("/accounts/register/", {}, REMOTE_ADDR="127.0.0.1", HTTP_X_REAL_IP="1.1.1.1").status_code == 429
    assert client.post("/accounts/register/", {}, REMOTE_ADDR="127.0.0.1", HTTP_X_REAL_IP="2.2.2.2").status_code == 200
