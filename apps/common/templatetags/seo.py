"""schema.org JSON-LD blocks for search engines (product rich results, breadcrumbs, store, articles).

Usage: {% load seo %} then e.g. {% json_ld_product product %} inside {% block seo %}.
"""
import json

from django import template
from django.conf import settings
from django.utils.safestring import mark_safe

from apps.common.services import get_settings

register = template.Library()

# keep "</script>" and friends inside strings from ending the script element
_SCRIPT_ESCAPES = {ord("<"): "\\u003C", ord(">"): "\\u003E", ord("&"): "\\u0026"}
_CONTEXT = "https://schema.org"


def _script(*blocks) -> str:
    html = "".join(
        '<script type="application/ld+json">'
        + json.dumps(block, ensure_ascii=False).translate(_SCRIPT_ESCAPES)
        + "</script>"
        for block in blocks
    )
    return mark_safe(html)


def _absolute(context, path: str) -> str:
    request = context.get("request")
    if request is not None:
        return request.build_absolute_uri(path)
    return settings.SITE_URL.rstrip("/") + path


def _organization(context) -> dict:
    return {"@type": "Organization", "name": get_settings().store_name, "url": _absolute(context, "/")}


def _breadcrumbs(context, crumbs) -> dict:
    return {
        "@context": _CONTEXT,
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": position, "name": name, "item": _absolute(context, url)}
            for position, (name, url) in enumerate(crumbs, start=1)
        ],
    }


@register.simple_tag(takes_context=True)
def json_ld_product(context, product):
    """Product with offer (price in IRR, as Google requires ISO currencies) and rating, plus its breadcrumb."""
    url = _absolute(context, product.get_absolute_url())
    data = {
        "@context": _CONTEXT,
        "@type": "Product",
        "name": product.name,
        "url": url,
        "sku": str(product.pk),
        "category": product.category.name,
        "offers": {
            "@type": "Offer",
            "url": url,
            "priceCurrency": "IRR",
            "price": product.effective_price * 10,  # stored in Toman
            "availability": "https://schema.org/InStock" if product.in_stock else "https://schema.org/OutOfStock",
            "itemCondition": "https://schema.org/NewCondition",
        },
    }
    variants = list(product.variants.filter(is_active=True)) if product.has_variants else []
    if variants:
        prices = [variant.effective_price * 10 for variant in variants]
        data["offers"] = {
            "@type": "AggregateOffer",
            "url": url,
            "priceCurrency": "IRR",
            "lowPrice": min(prices),
            "highPrice": max(prices),
            "offerCount": len(variants),
            "availability": "https://schema.org/InStock" if product.in_stock else "https://schema.org/OutOfStock",
            "itemCondition": "https://schema.org/NewCondition",
        }
    if product.sale_ends_at and product.on_sale:
        data["offers"]["priceValidUntil"] = product.sale_ends_at.date().isoformat()
    if product.description:
        data["description"] = product.description[:5000]
    images = [product.image.url] if product.image else []
    images += [img.image.url for img in product.images.all()]
    if images:
        data["image"] = [_absolute(context, src) for src in images]
    if product.brand_id:
        data["brand"] = {"@type": "Brand", "name": product.brand.name}

    rating = getattr(product, "avg_rating", None)
    count = getattr(product, "review_count", 0)
    if rating and count:
        data["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": round(float(rating), 1),
            "reviewCount": count,
            "bestRating": 5,
            "worstRating": 1,
        }

    crumbs = [("خانه", "/")]
    if product.category.parent_id:
        parent = product.category.parent
        crumbs.append((parent.name, parent.get_absolute_url()))
    crumbs += [(product.category.name, product.category.get_absolute_url()), (product.name, product.get_absolute_url())]
    return _script(data, _breadcrumbs(context, crumbs))


@register.simple_tag(takes_context=True)
def json_ld_listing_breadcrumbs(context, category_slug="", brand_name=""):
    """Home > products > (parent) > category or brand, for product listing pages."""
    from apps.catalog.models import Category

    request = context.get("request")
    current = request.path if request is not None else "/products/"
    crumbs = [("خانه", "/"), ("محصولات", "/products/")]
    category = Category.objects.select_related("parent").filter(slug=category_slug).first() if category_slug else None
    if category is not None:
        if category.parent_id:
            crumbs.append((category.parent.name, category.parent.get_absolute_url()))
        crumbs.append((category.name, category.get_absolute_url()))
    elif brand_name:
        crumbs.append((brand_name, current))
    return _script(_breadcrumbs(context, crumbs))


@register.simple_tag(takes_context=True)
def json_ld_store(context):
    """The shop itself (for the home page): OnlineStore with support phone, and the WebSite name."""
    store = get_settings()
    home = _absolute(context, "/")
    organization = {"@context": _CONTEXT, "@type": "OnlineStore", "name": store.store_name, "url": home}
    if store.contact_phone:
        organization["contactPoint"] = {
            "@type": "ContactPoint",
            "telephone": store.contact_phone,
            "contactType": "customer support",
            "availableLanguage": "fa",
        }
    website = {"@context": _CONTEXT, "@type": "WebSite", "name": store.store_name, "url": home, "inLanguage": "fa-IR"}
    return _script(organization, website)


@register.simple_tag(takes_context=True)
def json_ld_article(context, post):
    url = _absolute(context, post.get_absolute_url())
    published = post.published_at or post.created_at
    data = {
        "@context": _CONTEXT,
        "@type": "BlogPosting",
        "headline": post.title[:110],
        "url": url,
        "mainEntityOfPage": url,
        "inLanguage": "fa-IR",
        "datePublished": published.isoformat(),
        "author": _organization(context),
        "publisher": _organization(context),
    }
    if post.excerpt:
        data["description"] = post.excerpt
    if post.cover:
        data["image"] = [_absolute(context, post.cover.url)]
    crumbs = [("خانه", "/"), ("راهنمای خرید", "/blog/"), (post.title, post.get_absolute_url())]
    return _script(data, _breadcrumbs(context, crumbs))
