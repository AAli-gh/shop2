LAST_VISITED_LIMIT = 8


def record_view(request, product):
    """Track recently viewed product ids (slugs) in the session."""
    key = "last_visited"
    entries = request.session.get(key, [])
    slug = product.slug
    entries = [e for e in entries if e != slug]
    entries.insert(0, slug)
    request.session[key] = entries[:LAST_VISITED_LIMIT]


def get_viewed_products(request, exclude_slug=None):
    """Resolve session slugs into active Product objects, newest first."""
    from apps.catalog.models import Product

    slugs = request.session.get("last_visited", [])
    if exclude_slug:
        slugs = [s for s in slugs if s != exclude_slug]
    if not slugs:
        return []
    products = {p.slug: p for p in Product.objects.filter(slug__in=slugs, is_active=True)}
    return [products[s] for s in slugs if s in products]
