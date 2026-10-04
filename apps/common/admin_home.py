"""Data for the admin shell: the right-hand menu, the top bar and the dashboard home page.

Everything here is filtered by the signed-in staff member's permissions: a warehouse clerk sees
products and stock, not customers or money. Counts are worked out once per request.
"""
import math
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.db.models import BigIntegerField, Count, ExpressionWrapper, F, Sum
from django.db.models.functions import TruncDate
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

FA_MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
DONUT_COLORS = ["#2563eb", "#14b8a6", "#f59e0b", "#a855f7", "#ec4899", "#ef4444", "#94a3b8"]
AVATAR_COLORS = ["#0d5c75", "#7c3aed", "#db2777", "#ea580c", "#16a34a", "#2563eb", "#9333ea", "#0891b2"]


def _url(name, *args):
    try:
        return reverse(name, args=args)
    except NoReverseMatch:
        return ""


def _paid_statuses():
    from apps.orders.models import Order

    return [Order.Status.PAID, Order.Status.PROCESSING, Order.Status.SHIPPED, Order.Status.DELIVERED]


# ---------------------------------------------------------------- counters

COUNTERS = {
    # key: (permission, label, icon, colour, admin url name + query)
    "orders_today": ("orders.view_order", "سفارش‌های امروز", "cart", "green", ("admin:orders_order_changelist", "?created_at_jalali=today")),
    "ready": ("orders.view_order", "آماده پردازش", "clock", "orange", ("admin:orders_order_changelist", "?status__exact=paid")),
    "rep_awaiting": ("orders.view_order", "سفارش ویزیتور", "truck", "blue", ("admin:orders_order_changelist", "?status__exact=approval")),
    "returns": ("orders.view_returnrequest", "مرجوعی منتظر بررسی", "return", "red", ("admin:orders_returnrequest_changelist", "?status__exact=pending")),
    "out_of_stock": ("catalog.view_product", "محصول ناموجود", "cube", "red", ("admin:catalog_product_changelist", "?is_active__exact=1")),
    "running_out": ("catalog.view_product", "رو به اتمام (پیش‌بینی)", "warning", "orange", ("common:stock_forecast", "")),
    "missed_searches": ("catalog.view_searchterm", "جستجوی بی‌نتیجه", "search", "blue", ("common:missed_searches", "")),
    "reviews": ("reviews.view_review", "نظر در انتظار تأیید", "chat", "purple", ("admin:reviews_review_changelist", "?is_approved__exact=0")),
    "questions": ("reviews.view_productquestion", "پرسش بی‌پاسخ", "question", "purple", ("admin:reviews_productquestion_changelist", "?answered=no")),
    "contacts": ("common.view_contactmessage", "پیام تماس جدید", "mail", "blue", ("admin:common_contactmessage_changelist", "?is_read__exact=0")),
}


def _count(key, now):
    from apps.catalog.models import Product
    from apps.common.models import ContactMessage
    from apps.orders.models import Order, ReturnRequest
    from apps.reviews.models import ProductQuestion, Review

    today = timezone.make_aware(datetime.combine(timezone.localdate(now), time.min))
    if key == "orders_today":
        return Order.objects.filter(created_at__gte=today).exclude(status=Order.Status.CANCELLED).count()
    if key == "ready":
        return Order.objects.filter(status=Order.Status.PAID).count()
    if key == "rep_awaiting":
        return Order.objects.filter(status=Order.Status.AWAITING_APPROVAL).count()
    if key == "returns":
        return ReturnRequest.objects.filter(status=ReturnRequest.Status.PENDING).count()
    if key == "out_of_stock":
        return Product.objects.filter(is_active=True, stock=0).count()
    if key == "running_out":
        from apps.catalog.forecast import at_risk_count

        return at_risk_count(now)
    if key == "missed_searches":
        from apps.catalog.search_report import missed_count

        return missed_count(now)
    if key == "reviews":
        return Review.objects.filter(is_approved=False).count()
    if key == "questions":
        return ProductQuestion.objects.filter(answer="").count()
    if key == "contacts":
        return ContactMessage.objects.filter(is_read=False).count()
    raise KeyError(key)


def counters(request):
    """{key: {label, count, url, icon, colour}} for what this user may see; cached on the request."""
    cached = getattr(request, "_admin_counters", None)
    if cached is not None:
        return cached
    now = timezone.now()
    result = {}
    for key, (perm, label, icon, colour, (name, query)) in COUNTERS.items():
        if request.user.has_perm(perm):
            url = _url(name)
            result[key] = {"key": key, "label": label, "count": _count(key, now), "url": url + query if url else "",
                           "icon": icon, "colour": colour}
    request._admin_counters = result
    return result


def _orders_trend(now):
    from apps.orders.models import Order

    today = timezone.make_aware(datetime.combine(timezone.localdate(now), time.min))
    orders = Order.objects.exclude(status=Order.Status.CANCELLED)
    yesterday = orders.filter(created_at__gte=today - timedelta(days=1), created_at__lt=today).count()
    current = orders.filter(created_at__gte=today).count()
    if not yesterday:
        return None
    return round((current - yesterday) * 100 / yesterday)


# ---------------------------------------------------------------- menu

def _item(label, url, perm=None, badge=None, match=None):
    return {"label": label, "url": url, "perm": perm, "badge": badge, "match": match}


def menu_groups():
    """The menu as (title, icon, items); items carry the permission that shows them."""
    a = "admin:"
    return [
        ("داشبورد", "home", [_item("داشبورد", _url(a + "index"), match="exact")]),
        ("محصولات", "cube", [
            _item("همه محصولات", _url(a + "catalog_product_changelist"), "catalog.view_product"),
            _item("افزودن محصول", _url(a + "catalog_product_add"), "catalog.add_product"),
            _item("ورود گروهی از اکسل", _url(a + "catalog_product_import"), "catalog.add_product"),
            _item("برندها", _url(a + "catalog_brand_changelist"), "catalog.view_brand"),
            _item("مشخصه‌های فنی", _url(a + "catalog_attribute_changelist"), "catalog.view_attribute"),
            _item("درخواست‌های «خبرم کن»", _url(a + "catalog_restocknotification_changelist"), "catalog.view_restocknotification"),
        ]),
        ("دسته‌بندی‌ها", "squares", [_item("دسته‌بندی‌ها", _url(a + "catalog_category_changelist"), "catalog.view_category")]),
        ("سفارش‌ها", "cart", [
            _item("همه سفارش‌ها", _url(a + "orders_order_changelist"), "orders.view_order"),
            _item("آماده پردازش", _url(a + "orders_order_changelist") + "?status__exact=paid", "orders.view_order", "ready"),
            _item("سفارش ویزیتور منتظر تأیید", _url(a + "orders_order_changelist") + "?status__exact=approval", "orders.view_order", "rep_awaiting"),
            _item("روش‌های ارسال", _url(a + "orders_shippingmethod_changelist"), "orders.view_shippingmethod"),
        ]),
        ("مرجوعی‌ها", "return", [_item("درخواست‌های مرجوعی", _url(a + "orders_returnrequest_changelist"), "orders.view_returnrequest", "returns")]),
        ("ویزیتورها", "truck", [
            _item("ویزیتورها", _url(a + "reps_salesrep_changelist"), "reps.view_salesrep"),
            _item("مشتریان ویزیتورها", _url(a + "reps_repcustomer_changelist"), "reps.view_repcustomer"),
        ]),
        ("مشتریان", "users", [
            _item("کاربران", _url(a + "accounts_user_changelist"), "accounts.view_user"),
            _item("دسته‌بندی مشتریان", _url("common:customer_segments"), "accounts.view_user"),
            _item("نشانی‌ها", _url(a + "accounts_address_changelist"), "accounts.view_address"),
            _item("سبدهای خرید", _url(a + "cart_cart_changelist"), "cart.view_cart"),
            _item("علاقه‌مندی‌ها", _url(a + "wishlist_wishlistitem_changelist"), "wishlist.view_wishlistitem"),
        ]),
        ("کوپن و کارت هدیه", "gift", [
            _item("کوپن‌ها", _url(a + "discounts_coupon_changelist"), "discounts.view_coupon"),
            _item("کارت‌های هدیه", _url(a + "wallet_giftcard_changelist"), "wallet.view_giftcard"),
            _item("کیف‌های پول", _url(a + "wallet_wallet_changelist"), "wallet.view_wallet"),
            _item("تراکنش‌های کیف پول", _url(a + "wallet_wallettransaction_changelist"), "wallet.view_wallettransaction"),
        ]),
        ("باشگاه مشتریان", "star", [
            _item("اعضای باشگاه", _url(a + "loyalty_loyaltyaccount_changelist"), "loyalty.view_loyaltyaccount"),
            _item("تراکنش‌های امتیاز", _url(a + "loyalty_pointtransaction_changelist"), "loyalty.view_pointtransaction"),
        ]),
        ("بازاریابی و کمپین‌ها", "megaphone", [
            _item("کمپین‌های خبرنامه", _url(a + "newsletter_campaign_changelist"), "newsletter.view_campaign"),
            _item("مشترکان خبرنامه", _url(a + "newsletter_subscriber_changelist"), "newsletter.view_subscriber"),
            _item("بازگرداندن مشتری", _url(a + "crm_winbackmessage_changelist"), "crm.view_winbackmessage"),
            _item("بنرهای صفحه اول", _url(a + "catalog_banner_changelist"), "catalog.view_banner"),
        ]),
        ("محتوا", "document", [
            _item("نظرات", _url(a + "reviews_review_changelist"), "reviews.view_review", "reviews"),
            _item("پرسش‌های محصول", _url(a + "reviews_productquestion_changelist"), "reviews.view_productquestion", "questions"),
            _item("پیام‌های تماس", _url(a + "common_contactmessage_changelist"), "common.view_contactmessage", "contacts"),
            _item("مقالات", _url(a + "blog_post_changelist"), "blog.view_post"),
            _item("راهنمای انتخاب کالا", _url(a + "guides_buyingguide_changelist"), "guides.view_buyingguide"),
            _item("صفحات ثابت", _url(a + "common_staticpage_changelist"), "common.view_staticpage"),
        ]),
        ("گزارش‌ها", "chart", [
            _item("گزارش فروش و سود", _url("common:dashboard"), "orders.view_order"),
            _item("پیش‌بینی موجودی", _url("common:stock_forecast"), "catalog.view_product", "running_out"),
            _item("جستجوهای بی‌نتیجه", _url("common:missed_searches"), "catalog.view_searchterm", "missed_searches"),
            _item("عبارت‌های جستجو", _url(a + "catalog_searchterm_changelist"), "catalog.view_searchterm"),
            _item("مترادف‌های جستجو", _url(a + "catalog_searchsynonym_changelist"), "catalog.view_searchsynonym"),
        ]),
        ("تنظیمات", "cog", [
            _item("تنظیمات سایت", _url(a + "common_sitesettings_changelist"), "common.view_sitesettings"),
            _item("نقش‌های کارمندان", _url(a + "auth_group_changelist"), "auth.view_group"),
        ]),
        ("لاگ رویدادها", "book", [_item("لاگ رویدادها", _url("common:logs"), "superuser")]),
    ]


def sidebar(request):
    """Menu groups this user may open, each item with its badge, and which one is current."""
    user, path = request.user, request.path
    counts = counters(request)
    groups = []
    for title, icon, items in menu_groups():
        visible = []
        for item in items:
            if not item["url"]:
                continue
            perm = item["perm"]
            if perm == "superuser" and not user.is_superuser or perm not in (None, "superuser") and not user.has_perm(perm):
                continue
            base = item["url"].split("?")[0]
            active = path == base if item["match"] == "exact" or base == _url("admin:index") else path.startswith(base)
            badge = counts.get(item["badge"], {}).get("count", 0) if item["badge"] else 0
            visible.append({**item, "active": active and "?" not in item["url"], "badge": badge})
        if not visible:
            continue
        groups.append({
            "title": title, "icon": icon, "items": visible, "single": len(visible) == 1,
            "url": visible[0]["url"], "active": any(i["active"] for i in visible),
            "badge": sum(i["badge"] for i in visible),
        })
    return groups


def topbar(request):
    counts = counters(request)
    tasks = [c for c in counts.values() if c["count"] and c["key"] != "orders_today"]
    roles = "مدیر سیستم" if request.user.is_superuser else "، ".join(request.user.groups.values_list("name", flat=True)) or "کارمند"
    return {
        "tasks": tasks,
        "notifications": sum(t["count"] for t in tasks),
        "messages": counts.get("contacts"),
        "role": roles,
    }


# ---------------------------------------------------------------- dashboard

def _short_amount(value):
    """Axis label: «۱۵۰م» for 150 million Toman, «۸۰۰ه» for 800 thousand."""
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:g}میلیارد"
    if value >= 1_000_000:
        return f"{value / 1_000_000:g}م"
    if value >= 1_000:
        return f"{value / 1_000:g}ه"
    return str(int(value))


def _nice_ceiling(value):
    if value <= 0:
        return 1
    magnitude = 10 ** math.floor(math.log10(value))
    for step in (1, 2, 2.5, 5, 10):
        if value <= step * magnitude:
            return step * magnitude
    return 10 * magnitude


def _fa_day(day: date) -> str:
    import jdatetime

    j = jdatetime.date.fromgregorian(date=day)
    return f"{j.day} {FA_MONTHS[j.month - 1]}"


def sales_chart(days=30, now=None):
    """Daily sales (line) and profit (bars) of paid orders, laid out for an inline SVG."""
    from apps.orders.models import Order, OrderItem

    now = now or timezone.now()
    today = timezone.localdate(now)
    start = today - timedelta(days=days - 1)
    since = timezone.make_aware(datetime.combine(start, time.min))
    sales = dict(
        Order.objects.filter(status__in=_paid_statuses(), created_at__gte=since)
        .annotate(day=TruncDate("created_at")).values("day").annotate(total=Sum("total")).values_list("day", "total")
    )
    profit_expr = ExpressionWrapper((F("unit_price") - F("unit_cost")) * F("quantity"), output_field=BigIntegerField())
    profit = dict(
        OrderItem.objects.filter(order__status__in=_paid_statuses(), order__created_at__gte=since, unit_cost__isnull=False)
        .annotate(day=TruncDate("order__created_at")).values("day").annotate(total=Sum(profit_expr)).values_list("day", "total")
    )
    series = [(start + timedelta(days=i)) for i in range(days)]
    width, height, left, bottom, top = 640, 220, 48, 28, 12
    plot_w, plot_h = width - left - 8, height - bottom - top
    peak = _nice_ceiling(max([sales.get(d, 0) or 0 for d in series] + [1]))
    step = plot_w / max(days - 1, 1)
    bar_w = max(3, min(14, step * 0.55))

    def y(value):
        return top + plot_h - (max(value, 0) / peak) * plot_h

    points = []
    for i, day in enumerate(series):
        s, p = sales.get(day, 0) or 0, profit.get(day, 0) or 0
        x = left + i * step
        points.append({
            "x": round(x, 1), "y": round(y(s), 1), "bar_y": round(y(p), 1), "bar_h": round(top + plot_h - y(p), 1),
            "bar_x": round(x - bar_w / 2, 1), "sales": s, "profit": p, "label": _fa_day(day),
        })
    every = max(1, days // 8)
    return {
        "width": width, "height": height, "bar_w": round(bar_w, 1), "points": points,
        "line": " ".join(f"{p['x']},{p['y']}" for p in points),
        "area": f"{left},{top + plot_h} " + " ".join(f"{p['x']},{p['y']}" for p in points) + f" {points[-1]['x']},{top + plot_h}",
        "ticks": [{"y": round(y(peak * k / 4), 1), "label": _short_amount(peak * k / 4)} for k in range(5)],
        "x_labels": [p for i, p in enumerate(points) if i % every == 0 or i == days - 1],
        "baseline": top + plot_h, "left": left, "right": width - 8,
        "total_sales": sum(p["sales"] for p in points), "total_profit": sum(p["profit"] for p in points),
        "days": days,
    }


def category_share(days=30, now=None):
    """Sales by top-level category for the donut: up to six slices, the rest as «سایر»."""
    from apps.orders.models import OrderItem

    now = now or timezone.now()
    rows = (
        OrderItem.objects.filter(order__status__in=_paid_statuses(), order__created_at__gte=now - timedelta(days=days),
                                 product__isnull=False)
        .values("product__category__name", "product__category__parent__name")
        .annotate(total=Sum("line_total"))
    )
    by_category = {}
    for row in rows:
        name = row["product__category__parent__name"] or row["product__category__name"]
        by_category[name] = by_category.get(name, 0) + (row["total"] or 0)
    ranked = sorted(by_category.items(), key=lambda kv: -kv[1])
    if len(ranked) > 6:
        ranked = ranked[:5] + [("سایر", sum(v for _, v in ranked[5:]))]
    total = sum(v for _, v in ranked)
    circumference = 2 * math.pi * 60
    slices, offset = [], 0
    for i, (name, value) in enumerate(ranked):
        share = value / total if total else 0
        slices.append({
            "name": name, "value": value, "percent": round(share * 100),
            "colour": DONUT_COLORS[i % len(DONUT_COLORS)],
            "dash": f"{share * circumference:.2f} {circumference:.2f}", "offset": f"{-offset * circumference:.2f}",
        })
        offset += share
    if total >= 1_000_000_000:
        centre, unit = f"{total / 1_000_000_000:.1f}", "میلیارد تومان"
    else:
        centre, unit = f"{total / 1_000_000:.0f}", "میلیون تومان"
    return {"slices": slices, "total": total, "centre": centre, "unit": unit}


def stock_status():
    from apps.catalog.models import Product

    products = Product.objects.filter(is_active=True)
    threshold = getattr(settings, "LOW_STOCK_THRESHOLD", 3)
    return {
        "total": products.count(),
        "in_stock": products.filter(stock__gt=threshold).count(),
        "low": products.filter(stock__gt=0, stock__lte=threshold).count(),
        "out": products.filter(stock=0).count(),
    }


def _avatar(name: str):
    name = (name or "؟").strip()
    return {"initial": name[:1], "colour": AVATAR_COLORS[sum(map(ord, name)) % len(AVATAR_COLORS)]}


def latest_orders(limit=5):
    from apps.orders.models import Order

    orders = (
        Order.objects.select_related("user", "shipping_address", "rep_customer")
        .prefetch_related("items__product").order_by("-created_at")[:limit]
    )
    rows = []
    for order in orders:
        address = getattr(order, "shipping_address", None)
        name = (order.rep_customer.shop_name if order.rep_customer_id else None) or (address.full_name if address else "") \
            or order.user.name or str(order.user)
        rows.append({
            "order": order, "name": name, "avatar": _avatar(name),
            "products": [i.product for i in order.items.all() if i.product and i.product.image][:2],
            "url": _url("admin:orders_order_change", order.pk),
        })
    return rows


def best_sellers(days=30, limit=5, now=None):
    from apps.catalog.models import Product
    from apps.orders.models import OrderItem

    now = now or timezone.now()
    rows = list(
        OrderItem.objects.filter(order__status__in=_paid_statuses(), order__created_at__gte=now - timedelta(days=days),
                                 product__isnull=False)
        .values("product_id").annotate(units=Sum("quantity")).order_by("-units")[:limit]
    )
    if not rows:  # a new shop: fall back to all-time counters
        products = list(Product.objects.filter(is_active=True, sold_count__gt=0).select_related("category").order_by("-sold_count")[:limit])
        return [{"product": p, "units": p.sold_count, "url": _url("admin:catalog_product_change", p.pk)} for p in products]
    products = Product.objects.select_related("category").in_bulk([r["product_id"] for r in rows])
    return [
        {"product": products[r["product_id"]], "units": r["units"], "url": _url("admin:catalog_product_change", r["product_id"])}
        for r in rows if r["product_id"] in products
    ]


QUICK_LINKS = [
    ("افزودن محصول", "plus", "admin:catalog_product_add", "catalog.add_product", "green"),
    ("افزودن از اکسل", "upload", "admin:catalog_product_import", "catalog.add_product", "green"),
    ("خروجی محصولات", "download", "admin:catalog_product_export", "catalog.view_product", "purple"),
    ("مدیریت بنرها", "photo", "admin:catalog_banner_changelist", "catalog.view_banner", "blue"),
    ("نوشتن مقاله", "document", "admin:blog_post_add", "blog.add_post", "pink"),
    ("ایجاد کوپن", "gift", "admin:discounts_coupon_add", "discounts.add_coupon", "orange"),
    ("ارسال خبرنامه", "send", "admin:newsletter_campaign_add", "newsletter.add_campaign", "blue"),
    ("تنظیمات سایت", "cog", "admin:common_sitesettings_changelist", "common.view_sitesettings", "gray"),
]


def dashboard(request, days=30):
    user = request.user
    now = timezone.now()
    counts = counters(request)
    # in page order, right to left
    first_row = [counts[k] for k in ("returns", "rep_awaiting", "ready", "orders_today") if k in counts]
    second_row = [counts[k] for k in ("contacts", "questions", "reviews", "missed_searches", "running_out", "out_of_stock") if k in counts]
    can_money = user.has_perm("orders.view_order")
    can_catalog = user.has_perm("catalog.view_product")
    return {
        "first_row": first_row,
        "second_row": second_row,
        "orders_trend": _orders_trend(now) if "orders_today" in counts else None,
        "days": days,
        "chart": sales_chart(days, now) if can_money else None,
        "donut": category_share(days, now) if can_money else None,
        "stock": stock_status() if can_catalog else None,
        "latest": latest_orders() if can_money else [],
        "best": best_sellers(days, now=now) if can_catalog else [],
        "tasks": [c for c in counts.values() if c["key"] != "orders_today"],
        "quick": [
            {"label": label, "icon": icon, "url": _url(name), "colour": colour}
            for label, icon, name, perm, colour in QUICK_LINKS if user.has_perm(perm) and _url(name)
        ],
    }


def global_search(request, q: str, limit=6):
    """The top bar's search: orders, products, customers and shops this user may see."""
    from django.db.models import Q

    from apps.accounts.otp import normalize_phone
    from apps.common.text import normalize_search

    q = q.strip()
    if len(q) < 2:
        return []
    user, phone = request.user, normalize_phone(q)
    sections = []
    if user.has_perm("orders.view_order"):
        from apps.orders.models import Order

        orders = Order.objects.select_related("shipping_address").filter(
            Q(order_number__icontains=q) | Q(shipping_address__full_name__icontains=q)
            | Q(shipping_address__phone__in=[q, phone or q]) | Q(user__phone=phone or q)
        ).order_by("-created_at")[:limit]
        sections.append(("سفارش‌ها", [(o.order_number, getattr(o, "shipping_address", None) and o.shipping_address.full_name or "",
                                        _url("admin:orders_order_change", o.pk)) for o in orders]))
    if user.has_perm("catalog.view_product"):
        from apps.catalog.models import Product

        products = Product.objects.filter(search_text__contains=normalize_search(q)).order_by("-sold_count")[:limit]
        sections.append(("محصولات", [(p.name, f"موجودی {p.stock}", _url("admin:catalog_product_change", p.pk)) for p in products]))
    if user.has_perm("accounts.view_user"):
        from django.contrib.auth import get_user_model

        people = get_user_model().objects.filter(
            Q(email__icontains=q) | Q(name__icontains=q) | Q(phone=phone or q)
        )[:limit]
        sections.append(("مشتریان", [(p.name or str(p), p.phone or p.email or "", _url("admin:accounts_user_change", p.pk)) for p in people]))
    if user.has_perm("reps.view_repcustomer"):
        from apps.reps.models import RepCustomer

        shops = RepCustomer.objects.filter(Q(shop_name__icontains=q) | Q(phone__icontains=q) | Q(owner_name__icontains=q))[:limit]
        sections.append(("مغازه‌های ویزیتورها", [(s.shop_name, s.city, _url("admin:reps_repcustomer_change", s.pk)) for s in shops]))
    return [(title, rows) for title, rows in sections if rows]
