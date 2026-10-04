import pytest
from django.test import Client, override_settings


@pytest.mark.django_db
def test_custom_404_page():
    with override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"]):
        client = Client()
        resp = client.get("/nonexistent-page-xyz/")
        assert resp.status_code == 404
        content = resp.content.decode("utf-8")
        assert "صفحه موردنظر پیدا نشد" in content
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
