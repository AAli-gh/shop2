import pytest

from apps.catalog.models import Category, PriceAlert, Product
from apps.catalog.price_alerts import is_following, send_price_alerts, toggle
from apps.common.sms import LocmemSmsBackend


@pytest.fixture
def product(db):
    category = Category.objects.create(name="یخچال", slug="fridge")
    return Product.objects.create(category=category, name="یخچال ساید", slug="side", price=50_000_000, stock=3)


@pytest.fixture
def customer(django_user_model):
    return django_user_model.objects.create_user(phone="09121234567", phone_verified=True)


def _texts(phone="09121234567"):
    return [m["text"] for m in LocmemSmsBackend.outbox if m["phone"] == phone]


def test_toggle_follows_at_todays_price_and_unfollows(product, customer):
    assert toggle(user=customer, product=product) is True
    assert PriceAlert.objects.get().price_at_signup == 50_000_000
    assert is_following(customer, product)

    assert toggle(user=customer, product=product) is False
    assert not PriceAlert.objects.exists()


def test_a_price_drop_is_texted_once(product, customer):
    toggle(user=customer, product=product)
    product.sale_price = 45_000_000
    product.save()

    assert send_price_alerts() == 1
    (text,) = _texts()
    assert "یخچال ساید" in text and "45,000,000" in text and "/product/side/" in text

    assert send_price_alerts() == 0
    assert not is_following(customer, product)


@pytest.mark.parametrize("change", [{}, {"price": 55_000_000}, {"sale_price": 45_000_000, "stock": 0}])
def test_no_alert_unless_cheaper_and_in_stock(product, customer, change):
    toggle(user=customer, product=product)
    for field, value in change.items():
        setattr(product, field, value)
    product.save()

    assert send_price_alerts() == 0
    assert _texts() == []


def test_accounts_without_a_mobile_get_an_email(product, django_user_model, mailoutbox):
    shopper = django_user_model.objects.create_user(email="shopper@example.com", password="x")
    toggle(user=shopper, product=product)
    product.sale_price = 40_000_000
    product.save()

    assert send_price_alerts() == 1
    assert mailoutbox[0].to == ["shopper@example.com"] and "یخچال ساید" in mailoutbox[0].subject


def test_following_again_after_an_alert_starts_from_the_new_price(product, customer):
    toggle(user=customer, product=product)
    product.sale_price = 45_000_000
    product.save()
    send_price_alerts()

    assert toggle(user=customer, product=product) is True
    alert = PriceAlert.objects.get()
    assert (alert.price_at_signup, alert.notified_at) == (45_000_000, None)


@pytest.mark.django_db
def test_button_and_endpoint(client, product, customer):
    url = f"/product/{product.slug}/price-alert/"
    page = client.get(product.get_absolute_url()).content.decode()
    assert "اگر قیمت کم شد خبرم کن" in page and url not in page  # guests see a sign-in link
    assert client.post(url).status_code == 403

    client.force_login(customer)
    response = client.post(url).content.decode()
    assert 'aria-pressed="true"' in response
    assert "لغو" in client.get(product.get_absolute_url()).content.decode()
    assert client.get(url).status_code == 405
