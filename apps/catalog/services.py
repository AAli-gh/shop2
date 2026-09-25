from django.core.paginator import Paginator
from django.utils import timezone
from django.db.models import Avg, Case, Count, Exists, IntegerField, OuterRef, Q, Value, When

from apps.catalog.models import Attribute, Banner, Brand, Category, Product, ProductVariant
from apps.common.text import normalize_search

SORT_CHOICES = {
    "newest": "-created_at",
    "price_asc": "price",
    "price_desc": "-price",
}
# a search is sorted by how well it matches unless the customer picks another order
RELEVANCE = "relevance"


def default_sort(q=None) -> str:
    return RELEVANCE if q else "newest"

BASE_ANNOTATIONS = dict(
    avg_rating=Avg("reviews__rating", filter=Q(reviews__is_approved=True)),
    review_count=Count("reviews", distinct=True, filter=Q(reviews__is_approved=True)),
    # read by Product.has_variants: cards link to the page to pick a colour/option instead of adding directly
    has_variant_options=Exists(ProductVariant.objects.filter(product=OuterRef("pk"), is_active=True)),
)


def live_discount_q() -> Q:
    """Products whose discount is running right now (an open-ended discount always is)."""
    now = timezone.now()
    return (
        Q(sale_price__isnull=False)
        & (Q(sale_starts_at__isnull=True) | Q(sale_starts_at__lte=now))
        & (Q(sale_ends_at__isnull=True) | Q(sale_ends_at__gte=now))
    )


def _active_qs():
    return (
        Product.objects.filter(is_active=True)
        .select_related("category", "brand")
        .annotate(**BASE_ANNOTATIONS)
    )


def _search(qs, q):
    """Every word of the query must appear somewhere (any order), after folding spelling variants."""
    for term in normalize_search(q).split():
        qs = qs.filter(search_text__contains=term)
    return qs


def list_products(*, category_slug=None, brand_slug=None, q=None, sort=None, page=1,
                  per_page=12, min_price=None, max_price=None, filters=None,
                  in_stock=False, on_sale=False):
    qs = _active_qs()
    if category_slug:
        qs = qs.filter(Q(category__slug=category_slug) | Q(category__parent__slug=category_slug))
    if brand_slug:
        qs = qs.filter(brand__slug=brand_slug)
    if q:
        qs = _search(qs, q)
    if min_price is not None:
        qs = qs.filter(price__gte=min_price)
    if max_price is not None:
        qs = qs.filter(price__lte=max_price)
    if in_stock:
        qs = qs.filter(stock__gt=0)
    if on_sale:
        qs = qs.filter(live_discount_q())
    # advanced spec filters: {attribute_name: [value_text, ...]} — OR within an attribute
    for attr_name, values in (filters or {}).items():
        if not values:
            continue
        qs = qs.filter(
            attributes__attribute__name=attr_name,
            attributes__value_text__in=values,
        )
    sort = sort if sort in SORT_CHOICES or sort == RELEVANCE else default_sort(q)
    if sort == RELEVANCE and q:
        # a name that starts with the search beats one that merely mentions it; then best sellers
        folded = normalize_search(q)
        qs = qs.annotate(match_score=Case(
            When(search_text__startswith=folded, then=Value(2)),
            When(search_text__contains=folded, then=Value(1)),
            default=Value(0), output_field=IntegerField(),
        )).order_by("-match_score", "-sold_count", "-created_at")
    else:
        qs = qs.order_by(SORT_CHOICES.get(sort, SORT_CHOICES["newest"]))
    paginator = Paginator(qs.distinct(), per_page)
    return paginator.get_page(page)


def get_product_detail(slug):
    return _active_qs().filter(slug=slug).first()


def product_specs(product):
    """Ordered list of (attribute, display_value) rows for the detail page."""
    rows = list(product.attributes.select_related("attribute").order_by(
        "attribute__sort_order", "attribute__name"
    ))
    # split into a 2-column-friendly list
    return [{"attribute": v.attribute, "display": v.display()} for v in rows]


def filterable_attributes(category):
    """Filter groups for a category: each attribute with its distinct text values."""
    if category is None:
        return []
    attrs = Attribute.objects.filter(
        category=category, is_filterable=True, data_type=Attribute.DataType.TEXT
    ).prefetch_related("values").order_by("sort_order", "name")
    result = []
    for a in attrs:
        values = sorted({v.value_text for v in a.values.select_related("product").filter(
            value_text__isnull=False
        ) if v.value_text})
        if values:
            result.append({"attr": a, "values": values})
    return result


def top_categories():
    return Category.objects.filter(is_active=True, parent__isnull=True).prefetch_related("children")


def active_brands():
    return Brand.objects.filter(is_active=True)


def get_brand(slug):
    return Brand.objects.filter(slug=slug, is_active=True).first()


def price_bounds():
    """Min/max price across active products, for the range filter UI."""
    from django.db.models import Max, Min

    agg = Product.objects.filter(is_active=True).aggregate(
        min_price=Min("price"), max_price=Max("price")
    )
    return agg["min_price"] or 0, agg["max_price"] or 0


def featured_products(limit=4):
    return list(_active_qs().filter(is_featured=True)[:limit])


def on_sale_products(limit=4):
    return list(_active_qs().filter(live_discount_q())[:limit])


def flash_sale_products(limit=8):
    """Discounts with a deadline, the one ending soonest first."""
    return list(
        _active_qs().filter(live_discount_q(), sale_ends_at__gte=timezone.now()).order_by("sale_ends_at")[:limit]
    )


def personalized_products(request, limit=8):
    """Products from the categories this visitor has been looking at, or bought from before."""
    from apps.common import lastvisited

    viewed = lastvisited.get_viewed_products(request)
    category_ids = {product.category_id for product in viewed}
    seen_ids = {product.pk for product in viewed}

    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        from apps.orders.models import OrderItem

        bought = (
            OrderItem.objects.filter(order__user=user, product__isnull=False)
            .select_related("product").order_by("-id")[:10]
        )
        category_ids |= {item.product.category_id for item in bought}
        seen_ids |= {item.product_id for item in bought}

    if not category_ids:
        return []
    return list(
        _active_qs().filter(category_id__in=category_ids, stock__gt=0)
        .exclude(pk__in=seen_ids)
        .order_by("-sold_count", "-created_at")[:limit]
    )


def best_sellers(limit=4):
    return list(_active_qs().order_by("-sold_count", "-created_at")[:limit])


def active_banners():
    return Banner.objects.filter(is_active=True)


def quick_search(q, limit=6):
    """Light live-search results for the header dropdown."""
    if len(normalize_search(q)) < 2:
        return []
    return list(_search(_active_qs(), q).order_by("-sold_count")[:limit])


def related_products(product, limit=4):
    return list(
        _active_qs()
        .filter(category=product.category)
        .exclude(pk=product.pk)
        .order_by("-sold_count", "-created_at")[:limit]
    )


def home_categories(limit=6):
    """Top-level categories with the most active products, each with a cover image
    borrowed from one of its products (categories have no image of their own)."""
    categories = list(
        Category.objects.filter(is_active=True, parent__isnull=True)
        .annotate(active_count=Count("products", filter=Q(products__is_active=True)))
        .order_by("-active_count", "name")[:limit]
    )
    for category in categories:
        product = (
            Product.objects.filter(is_active=True)
            .filter(Q(category=category) | Q(category__parent=category))
            .exclude(image="")
            .only("image")
            .first()
        )
        category.cover_image = product.image if product else None
    return categories


def active_product_count():
    return Product.objects.filter(is_active=True).count()
