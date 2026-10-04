import pytest
from django.test import Client, override_settings


@pytest.mark.django_db
def test_custom_404_page():
    with override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"]):
        client = Client()
        resp = client.get("/nonexistent-page-xyz/")
        assert resp.status_code == 404
        content = resp.content.decode("utf-8")
        assert "صفحه مورد نظر پیدا نشد" in content
        assert "۴۰۴" in content


@pytest.mark.django_db
def test_about_page(client):
    resp = client.get("/about/")
    assert resp.status_code == 200
    assert "درباره" in resp.content.decode("utf-8")


@pytest.mark.django_db
def test_contact_form_submission(client):
    resp = client.post("/contact/", {
        "name": "کاربر",
        "email": "u@example.com",
        "subject": "موضوع",
        "body": "متن پیام آزمایشی",
    })
    assert resp.status_code == 302
    from apps.common.models import ContactMessage

    assert ContactMessage.objects.filter(email="u@example.com").exists()


@pytest.mark.django_db
def test_password_reset_flow(client, django_user_model):
    django_user_model.objects.create_user(email="reset@example.com", password="old12345")
    resp = client.post("/accounts/password-reset/", {"email": "reset@example.com"})
    assert resp.status_code == 302


@pytest.mark.django_db
def test_contact_message_is_emailed_to_the_shop(client, mailoutbox, settings):
    settings.ADMINS = [("Shop", "owner@example.com")]
    client.post("/contact/", {
        "name": "سارا", "email": "sara@example.com",
        "subject": "سؤال\nدرباره ارسال", "body": "سفارشم کی می‌رسد؟",
    })
    mail = mailoutbox[-1]
    assert mail.to == ["owner@example.com"]
    assert mail.reply_to == ["sara@example.com"]  # «Reply» answers the customer
    assert mail.subject == "پیام تماس: سؤال درباره ارسال"
    assert "سفارشم کی می‌رسد؟" in mail.body and "sara@example.com" in mail.body


def test_server_error_page_stands_alone():
    from django.template.loader import render_to_string

    html = render_to_string("500.html")  # what Django renders for a crash: no request, no context
    assert "خطای داخلی سرور" in html and "location.reload()" in html


@pytest.mark.django_db
def test_offline_page_and_service_worker(client):
    page = client.get("/offline/")
    assert page.status_code == 200 and "اتصال به اینترنت برقرار نیست" in page.content.decode()
    worker = client.get("/sw.js")
    assert worker["Content-Type"].startswith("application/javascript")
    assert '"/offline/"' in worker.content.decode()


@pytest.mark.django_db
def test_403_offers_sign_in_to_guests(client):
    with override_settings(DEBUG=False):
        page = client.get("/rep/")  # guests are redirected to sign in; a signed-in customer gets 403
    assert page.status_code == 302


@pytest.mark.django_db
def test_403_page_for_a_customer(client, django_user_model):
    client.force_login(django_user_model.objects.create_user(email="c@example.com", password="x"))
    body = client.get("/rep/").content.decode()
    assert "دسترسی غیرمجاز!" in body and "بازگشت به صفحه قبل" in body
