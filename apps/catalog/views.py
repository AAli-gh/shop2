from django.shortcuts import get_object_or_404, render

from apps.catalog import services
from apps.common import lastvisited
from apps.common.ratelimit import ratelimit


def home(request):
    flash_sale = services.flash_sale_products()
    return render(
        request,
        "catalog/home.html",
        {
            "banners": services.active_banners()[:2],
            "home_categories": services.home_categories(),
            "product_total": services.active_product_count(),
            "featured": services.featured_products(),
            "on_sale": services.on_sale_products(),
            "flash_sale": flash_sale,
            "flash_ends_at": flash_sale[0].sale_ends_at if flash_sale else None,
            "best_sellers": services.best_sellers(),
            "recently_viewed": lastvisited.get_viewed_products(request),
        },
    )


def live_search(request):
    q = request.GET.get("q", "")
    if len(q.strip()) < 2:
        return _search_suggestions(request)
    results = services.quick_search(q)
    return render(
        request,
        "catalog/partials/live_search_results.html",
        {"results": results, "q": q},
    )


def _parse_price(value):
    try:
        v = int(value)
        return v if v >= 0 else None
    except (TypeError, ValueError):
        return None


def product_list(request, category_slug=None, brand_slug=None):
    category = category_slug or request.GET.get("category")
    brand = brand_slug or request.GET.get("brand")
    min_price = _parse_price(request.GET.get("min_price"))
    max_price = _parse_price(request.GET.get("max_price"))
    # spec filters arrive as filter_<attrname> query params (multi-value per attribute)
    filters = {
        key[len("filter_"):]: [v for v in request.GET.getlist(key) if v]
        for key in request.GET
        if key.startswith("filter_") and request.GET.getlist(key)
    }
    only_in_stock = request.GET.get("stock") == "1"
    only_on_sale = request.GET.get("sale") == "1"
    products = services.list_products(
        category_slug=category,
        brand_slug=brand,
        q=request.GET.get("q"),
        sort=request.GET.get("sort"),
        page=request.GET.get("page"),
        min_price=min_price,
        max_price=max_price,
        filters=filters,
        in_stock=only_in_stock,
        on_sale=only_on_sale,
    )
    query = request.GET.get("q")
    if query and request.GET.get("page") in (None, "", "1"):
        from apps.catalog import search_history

        search_history.record_search(request, query, products.paginator.count)
    lo, hi = services.price_bounds()
    current_category_obj = None
    if category:
        from apps.catalog.models import Category

        current_category_obj = Category.objects.filter(slug=category).first()
    brand_obj = None
    if brand:
        brand_obj = services.get_brand(brand)
    # build spec filter groups with checked flags (avoid dict lookups by Persian keys in templates)
    spec_filters = []
    for group in services.filterable_attributes(current_category_obj):
        active = filters.get(group["attr"].name, [])
        spec_filters.append({
            "attr": group["attr"],
            "values": [{"value": v, "checked": v in active} for v in group["values"]],
        })
    return render(
        request,
        "catalog/product_list.html",
        {
            "products": products,
            "categories": services.top_categories(),
            "brands": services.active_brands(),
            "spec_filters": spec_filters,
            "current_category": category,
            "current_brand": brand,
            "current_brand_name": brand_obj.name if brand_obj else "",
            "current_sort": request.GET.get("sort") or "newest",
            "current_q": request.GET.get("q") or "",
            "only_in_stock": only_in_stock,
            "only_on_sale": only_on_sale,
            "active_filters": filters,
            "active_filter_pairs": [{"name": k, "value": v} for k, vs in filters.items() for v in vs],
            "min_price": min_price,
            "max_price": max_price,
            "price_lo": lo,
            "price_hi": hi,
        },
    )


@ratelimit("restock", limit=10, window=3600)
def restock_notify(request, slug):
    product = services.get_product_detail(slug)
    if product is None:
        from django.http import Http404

        raise Http404("محصول یافت نشد")

    from apps.catalog import restock

    result = restock.subscribe(product=product, email=request.POST.get("email", ""))
    return render(
        request,
        "catalog/partials/restock_result.html",
        {"product": product, "ok": result["ok"], "message": result["message"]},
    )


def compare_toggle(request, slug):
    from apps.catalog import compare

    try:
        result = compare.toggle(request, slug=slug)
        error = None
    except compare.CompareError as exc:
        result = {"added": False, "count": len(compare.get_slugs(request))}
        error = str(exc)
    return render(
        request,
        "catalog/partials/compare_result.html",
        {"slug": slug, "result": result, "error": error, "compare_count": result["count"]},
    )


def compare_remove(request, slug):
    from apps.catalog import compare

    compare.remove(request, slug)
    products = compare.get_products(request)
    return render(
        request,
        "catalog/partials/compare_table.html",
        {"products": products, "spec_rows": compare.spec_rows(products)},
    )


def compare_page(request):
    from apps.catalog import compare

    products = compare.get_products(request)
    return render(
        request,
        "catalog/compare.html",
        {"products": products, "spec_rows": compare.spec_rows(products)},
    )


def product_detail(request, slug):
    product = services.get_product_detail(slug)
    if product is None:
        from django.http import Http404

        raise Http404("محصول یافت نشد")

    from apps.catalog import price_alerts, video
    from apps.common import lastvisited
    from apps.reviews import services as review_services

    lastvisited.record_view(request, product)

    # ?v=<id> opens a given colour/option (shareable); otherwise the first one in stock
    variants = list(product.variants.filter(is_active=True)) if product.has_variants else []
    selected_variant = None
    if variants:
        wanted = request.GET.get("v", "")
        selected_variant = (
            next((v for v in variants if str(v.pk) == wanted), None)
            or next((v for v in variants if v.in_stock), variants[0])
        )

    return render(
        request,
        "catalog/product_detail.html",
        {
            "product": product,
            "variants": variants,
            "selected_variant": selected_variant,
            "offer": selected_variant or product,  # price and stock shown and sold
            "specs": services.product_specs(product),
            "reviews": review_services.approved_reviews_for(product),
            "questions": review_services.published_questions_for(product),
            "video_embed": video.embed_url(product.video_url),
            "following_price": price_alerts.is_following(request.user, product),
            "has_reviewed": (
                request.user.is_authenticated
                and review_services.has_reviewed(user=request.user, product=product)
            ),
            "related_products": services.related_products(product),
            "recently_viewed": lastvisited.get_viewed_products(request, exclude_slug=slug),
        },
    )


def brand_page(request, brand_slug):
    brand = services.get_brand(brand_slug)
    if brand is None:
        from django.http import Http404

        raise Http404("برند یافت نشد")
    return product_list(request, brand_slug=brand_slug)


def price_alert_toggle(request, slug):
    """Follow or unfollow a product's price (HTMX POST); guests get a sign-in link instead of the button."""
    from django.http import HttpResponse, HttpResponseNotAllowed
    from django.shortcuts import get_object_or_404, render

    from apps.catalog import price_alerts
    from apps.catalog.models import Product

    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if not request.user.is_authenticated:
        return HttpResponse(status=403)
    product = get_object_or_404(Product, slug=slug, is_active=True)
    following = price_alerts.toggle(user=request.user, product=product)
    return render(request, "catalog/partials/price_alert_button.html", {"product": product, "following_price": following})


def _search_suggestions(request):
    """Dropdown for the empty search box: recent searches, popular ones (or categories until there are some)."""
    from apps.catalog import search_history

    popular = search_history.popular_searches()
    return render(request, "catalog/partials/live_search_suggestions.html", {
        "recent": search_history.recent_searches(request),
        "popular": popular,
        "categories": [] if popular else list(services.top_categories()[:8]),
    })


def clear_recent_searches(request):
    from django.http import HttpResponseNotAllowed

    from apps.catalog import search_history

    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    search_history.clear_recent(request)
    return _search_suggestions(request)
