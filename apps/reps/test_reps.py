import pytest
from django.urls import reverse

from apps.catalog.models import Category, Product, ProductVariant
from apps.common.models import SiteSettings
from apps.orders.models import Order
from apps.orders.services import transition_status
from apps.reps.models import RepCustomer, SalesRep


@pytest.fixture
def product(db):
    category = Category.objects.create(name="یخچال", slug="fridge")
    return Product.objects.create(category=category, name="یخچال ساید", slug="side", price=50_000_000,
                                  wholesale_price=42_000_000, stock=10)


@pytest.fixture
def rep(django_user_model):
    user = django_user_model.objects.create_user(phone="09121230000", phone_verified=True, name="رضا ویزیتور")
    return SalesRep.objects.create(user=user, code="R01", region="تهران غرب")


@pytest.fixture
def shop(rep):
    return RepCustomer.objects.create(rep=rep, shop_name="لوازم خانگی امید", owner_name="آقای امیدی",
                                      phone="09125550000", province="تهران", city="تهران", address="خیابان آزادی")


@pytest.fixture
def signed_in(client, rep):
    client.force_login(rep.user)
    return client


def add(client, product, quantity=1, variant=None):
    data = {"product": product.pk, "quantity": quantity}
    if variant:
        data["variant"] = variant.pk
    return client.post(reverse("reps:basket_add"), data)


def place(client, shop, terms="cheque", note=""):
    return client.post(reverse("reps:basket"), {"customer": shop.pk, "payment_terms": terms, "note": note})


# ---------------------------------------------------------------- who gets in

def test_customers_and_guests_stay_out(client, django_user_model):
    assert client.get("/rep/").status_code == 302  # to the sign-in page
    client.force_login(django_user_model.objects.create_user(email="buyer@example.com", password="x"))
    assert client.get("/rep/").status_code == 403
    assert "data-rep-link" not in client.get("/").content.decode()


def test_inactive_rep_loses_the_panel(client, rep):
    rep.is_active = False
    rep.save()
    client.force_login(rep.user)
    assert client.get("/rep/").status_code == 403


def test_rep_sees_the_panel_button_and_pages(signed_in, product, shop):
    assert "data-rep-link" in signed_in.get("/").content.decode()
    for url in ("/rep/", "/rep/products/", f"/rep/products/{product.pk}/", "/rep/basket/", "/rep/orders/",
                "/rep/customers/", "/rep/customers/new/", f"/rep/customers/{shop.pk}/edit/"):
        assert signed_in.get(url).status_code == 200, url


# ---------------------------------------------------------------- ordering

def test_order_at_wholesale_price_reserves_stock_and_waits_for_approval(
        signed_in, rep, shop, product, mailoutbox, settings, django_capture_on_commit_callbacks):
    settings.ADMINS = [("Office", "office@example.com")]
    add(signed_in, product, 3)
    with django_capture_on_commit_callbacks(execute=True):
        response = place(signed_in, shop, note="تحویل پنجشنبه")

    order = Order.objects.get()
    assert response.url == reverse("reps:order_detail", args=[order.order_number])
    assert order.status == Order.Status.AWAITING_APPROVAL
    assert order.sales_rep == rep and order.rep_customer == shop and order.user == rep.user
    assert order.total == 3 * 42_000_000 and order.payment_terms == "cheque"
    assert order.shipping_address.address_line == "خیابان آزادی"
    product.refresh_from_db()
    assert product.stock == 7
    office = [mail for mail in mailoutbox if mail.to == ["office@example.com"]]
    assert office and order.order_number in office[-1].subject and "لوازم خانگی امید" in office[-1].body
    assert signed_in.get("/rep/basket/").context["basket"]["lines"] == []  # emptied


def test_site_price_when_no_wholesale_price(signed_in, shop, product):
    Product.objects.filter(pk=product.pk).update(wholesale_price=None)
    add(signed_in, product, 1)
    place(signed_in, shop)
    assert Order.objects.get().total == 50_000_000


def test_variant_wholesale_price(signed_in, shop, product):
    white = ProductVariant.objects.create(product=product, color_name="سفید", price=51_000_000,
                                          wholesale_price=40_000_000, stock=4)
    add(signed_in, product, 1)  # a product with variants needs one picked
    assert not signed_in.session.get("rep_basket")
    add(signed_in, product, 2, variant=white)
    place(signed_in, shop)
    order = Order.objects.get()
    assert order.total == 80_000_000
    white.refresh_from_db()
    assert white.stock == 2


def test_more_than_in_stock_is_refused(signed_in, shop, product):
    add(signed_in, product, 50)
    response = place(signed_in, shop)
    assert response.status_code == 200
    assert not Order.objects.exists()
    product.refresh_from_db()
    assert product.stock == 10


def test_reps_only_reach_their_own_shops_and_orders(client, signed_in, rep, shop, product, django_user_model):
    other_user = django_user_model.objects.create_user(phone="09121239999", phone_verified=True)
    other = SalesRep.objects.create(user=other_user, code="R02")
    their_shop = RepCustomer.objects.create(rep=other, shop_name="دیگری", phone="0912", province="ت", city="ت", address="الف")

    add(signed_in, product, 1)
    place(signed_in, their_shop)  # not in this rep's list
    assert not Order.objects.exists()
    assert signed_in.get(f"/rep/customers/{their_shop.pk}/edit/").status_code == 404

    place(signed_in, shop)
    mine = Order.objects.get()
    client.force_login(other_user)
    assert client.get(f"/rep/orders/{mine.order_number}/").status_code == 404


def test_rep_cancels_before_approval_only(signed_in, shop, product):
    add(signed_in, product, 2)
    place(signed_in, shop)
    order = Order.objects.get()

    signed_in.post(reverse("reps:order_cancel", args=[order.order_number]))
    order.refresh_from_db()
    product.refresh_from_db()
    assert order.status == Order.Status.CANCELLED and product.stock == 10

    add(signed_in, product, 1)
    place(signed_in, shop)
    approved = Order.objects.exclude(pk=order.pk).get()
    transition_status(order=approved, new_status=Order.Status.PROCESSING)
    signed_in.post(reverse("reps:order_cancel", args=[approved.order_number]))
    approved.refresh_from_db()
    assert approved.status == Order.Status.PROCESSING


def test_reorder_refills_the_basket(signed_in, shop, product):
    add(signed_in, product, 2)
    place(signed_in, shop)
    order = Order.objects.get()
    signed_in.post(reverse("reps:order_reorder", args=[order.order_number]))
    assert signed_in.session["rep_basket"] == {f"{product.pk}:0": 2}


def test_new_customer_from_the_panel(signed_in, rep):
    signed_in.post(reverse("reps:customer_new"), {
        "shop_name": "فروشگاه نور", "phone": "09120001111", "province": "البرز", "city": "کرج",
        "address": "میدان آزادگان", "is_active": "on",
    })
    assert RepCustomer.objects.get().rep == rep


# ---------------------------------------------------------------- company side

def test_approval_moves_to_processing_never_to_paid(signed_in, shop, product):
    from apps.orders.services import OrderError

    add(signed_in, product, 1)
    place(signed_in, shop)
    order = Order.objects.get()
    with pytest.raises(OrderError):
        transition_status(order=order, new_status=Order.Status.PAID)
    assert [s["label"] for s in order.progress_steps][:2] == ["در انتظار تأیید شرکت", "در حال پردازش"]


def test_rep_orders_are_not_the_reps_own_purchases(signed_in, rep, shop, product):
    from apps.crm.segments import segments_report
    from apps.loyalty.models import PointTransaction

    SiteSettings.objects.filter(pk=SiteSettings.load().pk).update(loyalty_enabled=True)
    add(signed_in, product, 1)
    place(signed_in, shop)
    order = Order.objects.get()
    for step in (Order.Status.PROCESSING, Order.Status.SHIPPED, Order.Status.DELIVERED):
        order = transition_status(order=order, new_status=step)

    assert not PointTransaction.objects.exists()
    assert sum(row["customers"] for row in segments_report()["summary"]) == 0


def test_shop_pages_never_show_the_wholesale_price(client, product):
    page = client.get(product.get_absolute_url()).content.decode()
    assert "42,000,000" not in page and "۴۲,۰۰۰,۰۰۰" not in page
