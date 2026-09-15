from django.core.paginator import Paginator
from django.db.models import Avg, Count, Exists, OuterRef, Q

from apps.catalog.models import Attribute, Banner, Brand, Category, Product, ProductVariant
from apps.common.text import normalize_search

SORT_CHOICES = {
    "newest": "-created_at",
    "price_asc": "price",
    "price_desc": "-price",
}

BASE_ANNOTATIONS = dict(
    avg_rating=Avg("reviews__rating", filter=Q(reviews__is_approved=True)),
    review_count=Count("reviews", distinct=True, filter=Q(reviews__is_approved=True)),
    # read by Product.has_variants: cards link to the page to pick a colour/option instead of adding directly
    has_variant_options=Exists(ProductVariant.objects.filter(product=OuterRef("pk"), is_active=True)),
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
                  per_page=12, min_price=None, max_price=None, filters=None):
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
    # advanced spec filters: {attribute_name: [value_text, ...]} — OR within an attribute
    for attr_name, values in (filters or {}).items():
        if not values:
            continue
        qs = qs.filter(
            attributes__attribute__name=attr_name,
            attributes__value_text__in=values,
        )
    order_by = SORT_CHOICES.get(sort, SORT_CHOICES["newest"])
    qs = qs.order_by(order_by)
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
    return list(_active_qs().filter(sale_price__isnull=False)[:limit])


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
