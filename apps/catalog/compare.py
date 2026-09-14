COMPARE_LIMIT = 3
SESSION_KEY = "compare"


class CompareError(Exception):
    pass


def get_slugs(request) -> list:
    return request.session.get(SESSION_KEY, [])


def toggle(request, slug: str) -> dict:
    slugs = get_slugs(request)
    if slug in slugs:
        slugs.remove(slug)
        added = False
    else:
        if len(slugs) >= COMPARE_LIMIT:
            raise CompareError(f"حداکثر {COMPARE_LIMIT} محصول قابل مقایسه است.")
        slugs.append(slug)
        added = True
    request.session[SESSION_KEY] = slugs
    return {"added": added, "count": len(slugs)}


def remove(request, slug: str) -> int:
    """Remove a product from the comparison regardless of add/remove state. Returns remaining count."""
    slugs = [s for s in get_slugs(request) if s != slug]
    request.session[SESSION_KEY] = slugs
    return len(slugs)


def clear(request) -> None:
    request.session[SESSION_KEY] = []


def get_products(request):
    from apps.catalog.models import Product

    slugs = get_slugs(request)
    if not slugs:
        return []
    products = {p.slug: p for p in Product.objects.filter(slug__in=slugs, is_active=True)}
    ordered = [products[s] for s in slugs if s in products]
    from apps.catalog.services import product_specs

    for p in ordered:
        p._specs = {row["attribute"].name: row["display"] for row in product_specs(p)}
    return ordered


def spec_rows(products):
    """Ordered list of {name, cells:[value_per_product]} across the compared products."""
    from apps.catalog.models import Attribute

    names, seen = [], set()
    for p in products:
        for name in getattr(p, "_specs", {}).keys():
            if name not in seen:
                seen.add(name)
                names.append(name)
    order = {a.name: a.sort_order for a in Attribute.objects.filter(name__in=names)}
    names.sort(key=lambda n: order.get(n, 999))
    return [{"name": n, "cells": [getattr(p, "_specs", {}).get(n, "—") for p in products]} for n in names]
