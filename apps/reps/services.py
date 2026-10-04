"""Sales-rep orders: a rep fills a basket from the catalogue at wholesale prices and places it for one
of their shops. The order reserves stock at once and waits for the company's approval; it is paid on
account (cash on delivery, cheque or credit), never through the online gateway.
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

SESSION_BASKET = "rep_basket"
MAX_QUANTITY = 999


class RepOrderError(Exception):
    pass


def active_rep(user):
    """The signed-in user's SalesRep if it is active, else None."""
    if not getattr(user, "is_authenticated", False):
        return None
    from apps.reps.models import SalesRep

    return SalesRep.objects.filter(user=user, is_active=True).select_related("user").first()


# ---------------------------------------------------------------- basket (in the session)

def _key(product_id: int, variant_id: int | None) -> str:
    return f"{product_id}:{variant_id or 0}"


def basket(session) -> dict[str, int]:
    return dict(session.get(SESSION_BASKET, {}))


def set_quantity(session, *, product_id: int, variant_id: int | None, quantity: int) -> None:
    items = basket(session)
    key = _key(product_id, variant_id)
    if quantity <= 0:
        items.pop(key, None)
    else:
        items[key] = min(quantity, MAX_QUANTITY)
    session[SESSION_BASKET] = items


def add(session, *, product_id: int, variant_id: int | None, quantity: int) -> None:
    current = basket(session).get(_key(product_id, variant_id), 0)
    set_quantity(session, product_id=product_id, variant_id=variant_id, quantity=current + max(quantity, 0))


def clear(session) -> None:
    session.pop(SESSION_BASKET, None)


def basket_lines(session) -> dict:
    """Priced lines of the basket; products that went inactive are dropped from it."""
    from apps.catalog.models import Product, ProductVariant

    items = basket(session)
    ids = {int(k.split(":")[0]) for k in items}
    variant_ids = {int(k.split(":")[1]) for k in items} - {0}
    products = Product.objects.filter(pk__in=ids, is_active=True).in_bulk()
    variants = ProductVariant.objects.filter(pk__in=variant_ids, is_active=True).in_bulk()
    lines, total, stale = [], 0, []
    for key, quantity in items.items():
        product_id, variant_id = (int(part) for part in key.split(":"))
        product = products.get(product_id)
        variant = variants.get(variant_id) if variant_id else None
        if product is None or (variant_id and (variant is None or variant.product_id != product_id)):
            stale.append(key)
            continue
        offer = variant or product
        unit = offer.rep_price
        lines.append({
            "key": key, "product": product, "variant": variant, "quantity": quantity,
            "unit_price": unit, "line_total": unit * quantity, "stock": offer.stock,
            "short": quantity > offer.stock,
        })
        total += unit * quantity
    if stale:
        session[SESSION_BASKET] = {k: v for k, v in items.items() if k not in stale}
    return {"lines": lines, "total": total, "count": sum(line["quantity"] for line in lines)}


# ---------------------------------------------------------------- placing an order

@transaction.atomic
def place_rep_order(*, rep, customer, lines: list[tuple[int, int | None, int]], payment_terms: str, note: str = ""):
    """Create the order for `customer` from (product_id, variant_id, quantity) lines and reserve the stock."""
    from apps.catalog.models import Product, ProductVariant
    from apps.catalog.stock import take_stock
    from apps.orders.models import Order, OrderItem, ShippingAddress
    from apps.orders.services import generate_order_number

    if customer.rep_id != rep.pk or not customer.is_active:
        raise RepOrderError("این مشتری در فهرست شما نیست.")
    if payment_terms not in Order.PaymentTerms.values:
        raise RepOrderError("نحوه پرداخت را انتخاب کنید.")
    lines = [(p, v, q) for p, v, q in lines if q > 0]
    if not lines:
        raise RepOrderError("سبد سفارش خالی است.")

    products = Product.objects.select_for_update().filter(pk__in={p for p, _, _ in lines}, is_active=True).in_bulk()
    variants = ProductVariant.objects.select_for_update().filter(pk__in={v for _, v, _ in lines if v}, is_active=True).in_bulk()
    rows, subtotal = [], 0
    for product_id, variant_id, quantity in lines:
        product = products.get(product_id)
        variant = variants.get(variant_id) if variant_id else None
        if product is None or (variant_id and (variant is None or variant.product_id != product_id)):
            raise RepOrderError("یکی از کالاهای سبد دیگر فروخته نمی‌شود؛ آن را حذف کنید.")
        if product.has_variants and variant is None:
            raise RepOrderError(f"برای «{product.name}» رنگ یا مدل را انتخاب کنید.")
        offer = variant or product
        name = f"{product.name} — {variant.label}" if variant else product.name
        if quantity > offer.stock:
            raise RepOrderError(f"از «{name}» فقط {offer.stock} عدد موجود است.")
        unit = offer.rep_price
        subtotal += unit * quantity
        rows.append({
            "product": product, "variant": variant, "product_name": name[:200],
            "variant_label": variant.label if variant else "", "unit_price": unit,
            "unit_cost": product.cost_price, "quantity": quantity, "line_total": unit * quantity,
        })

    order = Order.objects.create(
        order_number=generate_order_number(), user=rep.user, status=Order.Status.AWAITING_APPROVAL,
        items_subtotal=subtotal, total=subtotal, sales_rep=rep, rep_customer=customer,
        payment_terms=payment_terms, shipping_note=note.strip()[:200],
    )
    ShippingAddress.objects.create(
        order=order, full_name=(f"{customer.shop_name} — {customer.owner_name}" if customer.owner_name else customer.shop_name)[:120],
        phone=customer.phone, province=customer.province, city=customer.city,
        postal_code=customer.postal_code, address_line=customer.address,
    )
    for row in rows:
        OrderItem.objects.create(order=order, **row)
        left = take_stock(product_id=row["product"].pk, variant_id=row["variant"].pk if row["variant"] else None,
                          quantity=row["quantity"])
        if left is None:
            raise RepOrderError(f"موجودی «{row['product_name']}» همین حالا تمام شد.")

    from apps.common import shoplog
    from apps.reps.notifications import rep_order_placed

    shoplog.order_placed(order)
    transaction.on_commit(lambda: rep_order_placed(order))
    return order


def place_from_basket(session, *, rep, customer, payment_terms: str, note: str = ""):
    lines = [
        (int(key.split(":")[0]), int(key.split(":")[1]) or None, quantity)
        for key, quantity in basket(session).items()
    ]
    order = place_rep_order(rep=rep, customer=customer, lines=lines, payment_terms=payment_terms, note=note)
    clear(session)
    return order


def reorder_into_basket(session, order) -> int:
    """Put a past order's items back in the basket (products still sold); returns how many lines came back."""
    added = 0
    for item in order.items.filter(product__is_active=True):
        add(session, product_id=item.product_id, variant_id=item.variant_id, quantity=item.quantity)
        added += 1
    return added


def cancel_rep_order(*, rep, order):
    """A rep may withdraw an order the company hasn't approved yet; its stock goes back on sale."""
    from apps.orders.models import Order
    from apps.orders.services import OrderError, transition_status

    if order.sales_rep_id != rep.pk:
        raise RepOrderError("این سفارش متعلق به شما نیست.")
    if order.status != Order.Status.AWAITING_APPROVAL:
        raise RepOrderError("فقط سفارشی که هنوز تأیید نشده قابل لغو است.")
    try:
        return transition_status(order=order, new_status=Order.Status.CANCELLED)
    except OrderError as exc:
        raise RepOrderError(str(exc)) from exc


# ---------------------------------------------------------------- numbers for the panel

def dashboard(rep, now=None) -> dict:
    from apps.orders.models import Order, OrderItem

    now = now or timezone.now()
    month_start = timezone.localtime(now).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    orders = rep.orders.exclude(status=Order.Status.CANCELLED)
    this_month = orders.filter(created_at__gte=month_start)
    last_30 = orders.filter(created_at__gte=now - timedelta(days=30))
    month = this_month.aggregate(total=Sum("total"), count=Count("id"))
    top_products = (
        OrderItem.objects.filter(order__in=last_30).values("product_name")
        .annotate(units=Sum("quantity"), revenue=Sum("line_total")).order_by("-revenue")[:5]
    )
    top_customers = (
        rep.customers.filter(orders__in=last_30).annotate(revenue=Sum("orders__total"), count=Count("orders"))
        .order_by("-revenue")[:5]
    )
    return {
        "month_total": month["total"] or 0,
        "month_count": month["count"] or 0,
        "awaiting": orders.filter(status=Order.Status.AWAITING_APPROVAL).count(),
        "customers": rep.customers.filter(is_active=True).count(),
        "recent": rep.orders.select_related("rep_customer").order_by("-created_at")[:8],
        "top_products": list(top_products),
        "top_customers": list(top_customers),
    }


def catalogue(*, q: str = "", category: str = "", in_stock: bool = False):
    from apps.catalog.models import Product
    from apps.catalog.services import _search

    products = (
        Product.objects.filter(is_active=True).select_related("category", "brand")
        .prefetch_related("variants").order_by("category__name", "name")
    )
    if q:
        products = _search(products, q)
    if category:
        products = products.filter(Q(category__slug=category) | Q(category__parent__slug=category))
    if in_stock:
        products = products.filter(stock__gt=0)
    return products
