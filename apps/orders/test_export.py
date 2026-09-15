import io
import re

import openpyxl
import pytest

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product
from apps.orders.export import COLUMNS
from apps.orders.services import place_order

ADDRESS = {
    "full_name": "مریم احمدی", "phone": "09121234567", "province": "تهران",
    "city": "تهران", "postal_code": "1234567890", "address_line": "خیابان آزادی",
}


@pytest.mark.django_db
def test_orders_export_for_accounting(admin_client, django_user_model):
    customer = django_user_model.objects.create_user(email="buyer@example.com", password="x")
    category = Category.objects.create(name="c", slug="c")
    product = Product.objects.create(category=category, name="همزن", slug="mixer", price=2_000_000, stock=5)
    cart = Cart.objects.create(user=customer)
    CartItem.objects.create(cart=cart, product=product, quantity=2)
    order = place_order(user=customer, cart=cart, address_data=ADDRESS)

    response = admin_client.post("/admin/orders/order/", {"action": "export_excel", "_selected_action": [order.pk]})

    assert response["Content-Type"].startswith("application/vnd.openxmlformats")
    sheet = openpyxl.load_workbook(io.BytesIO(response.content))["سفارش‌ها"]
    assert sheet.sheet_view.rightToLeft
    assert [c.value for c in sheet[1]] == [title for title, _ in COLUMNS]
    row = {title: cell.value for (title, _), cell in zip(COLUMNS, sheet[2])}
    assert row["شماره سفارش"] == order.order_number
    assert re.match(r"^1[34]\d\d/\d\d/\d\d \d\d:\d\d$", row["تاریخ ثبت"])
    assert (row["نام گیرنده"], row["موبایل گیرنده"], row["شهر"]) == ("مریم احمدی", "09121234567", "تهران")
    assert row["کالاها"] == "همزن × 2"
    assert row["مبلغ کل"] == order.total

    totals = [cell.value for cell in sheet[3]]
    total_column = [title for title, _ in COLUMNS].index("مبلغ کل")
    assert totals[0] == "جمع" and totals[total_column] == "=SUM(P2:P2)"
