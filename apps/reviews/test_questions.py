import pytest

from apps.catalog.models import Category, Product
from apps.common.sms import LocmemSmsBackend
from apps.reviews.models import ProductQuestion

QUESTION = "ابعاد این یخچال دقیقاً چند سانتی‌متر است؟"


@pytest.fixture
def product(db):
    category = Category.objects.create(name="یخچال", slug="fridge")
    return Product.objects.create(category=category, name="یخچال ساید", slug="side", price=50_000_000, stock=3)


@pytest.fixture
def customer(django_user_model):
    return django_user_model.objects.create_user(phone="09121234567", phone_verified=True, name="مریم")


def _ask_url(product):
    return f"/reviews/product/{product.pk}/ask/"


def _answer(admin_client, question, answer, publish=True):
    data = {"answer": answer}
    if publish:
        data["is_published"] = "on"
    return admin_client.post(f"/admin/reviews/productquestion/{question.pk}/change/", data)


def test_guests_are_sent_to_login(client, product):
    response = client.post(_ask_url(product), {"body": QUESTION})
    assert response.status_code == 302 and "/accounts/login/" in response["Location"]
    assert not ProductQuestion.objects.exists()


def test_a_question_stays_hidden_until_answered(client, product, customer):
    client.force_login(customer)

    response = client.post(_ask_url(product), {"body": QUESTION})

    assert "پرسش شما ثبت شد" in response.content.decode()
    question = ProductQuestion.objects.get()
    assert (question.user, question.is_published, question.answer) == (customer, False, "")
    assert QUESTION not in client.get(product.get_absolute_url()).content.decode()


def test_too_short_questions_are_rejected(client, product, customer):
    client.force_login(customer)
    response = client.post(_ask_url(product), {"body": "ابعاد؟"})
    assert "کوتاه" in response.content.decode()
    assert not ProductQuestion.objects.exists()


def test_first_answer_publishes_and_texts_the_customer(admin_client, client, product, customer):
    question = ProductQuestion.objects.create(product=product, user=customer, body=QUESTION)

    response = _answer(admin_client, question, "۹۰ در ۱۸۰ سانتی‌متر.", publish=False)

    assert response.status_code == 302
    question.refresh_from_db()
    assert question.is_published and question.answered_by.is_superuser and question.answered_at
    texts = [m["text"] for m in LocmemSmsBackend.outbox if m["phone"] == "09121234567"]
    assert len(texts) == 1 and "یخچال ساید" in texts[0]
    page = client.get(product.get_absolute_url()).content.decode()
    assert QUESTION in page and "۹۰ در ۱۸۰ سانتی‌متر." in page

    _answer(admin_client, question, "۹۰ در ۱۸۰ سانتی‌متر، عمق ۷۰.")
    assert len([m for m in LocmemSmsBackend.outbox if m["phone"] == "09121234567"]) == 1  # no second text


def test_email_accounts_get_the_answer_by_email(admin_client, product, django_user_model, mailoutbox):
    asker = django_user_model.objects.create_user(email="asker@example.com", password="x")
    question = ProductQuestion.objects.create(product=product, user=asker, body=QUESTION)

    _answer(admin_client, question, "۹۰ در ۱۸۰ سانتی‌متر.")

    assert [m.to for m in mailoutbox] == [["asker@example.com"]]
    assert "یخچال ساید" in mailoutbox[0].subject


def test_staff_can_hide_an_answered_question(admin_client, client, product, customer):
    question = ProductQuestion.objects.create(product=product, user=customer, body=QUESTION)
    _answer(admin_client, question, "پاسخ اول")
    _answer(admin_client, question, "پاسخ اول", publish=False)

    question.refresh_from_db()
    assert not question.is_published
    assert QUESTION not in client.get(product.get_absolute_url()).content.decode()


def test_admin_home_counts_unanswered_questions(admin_client, product, customer):
    ProductQuestion.objects.create(product=product, user=customer, body=QUESTION)
    body = admin_client.get("/admin/").content.decode()
    assert "پرسش بی‌پاسخ" in body
    assert "/admin/reviews/productquestion/?answered=no" in body
    assert admin_client.get("/admin/reviews/productquestion/?answered=no").status_code == 200
