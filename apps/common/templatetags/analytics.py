"""Shopping events for Google Analytics 4, emitted only when a measurement ID is set in site settings.

Prices go out in IRR (Toman × 10), the ISO currency, as in the structured data. Each tag renders a
small <script> that calls window.shopTrack (defined in partials/analytics_head.html); HTMX runs
scripts in swapped content, so the add-to-cart feedback partial can report the event too.
"""
import json

from django import template
from django.utils.safestring import mark_safe

from apps.common.templatetags.seo import _SCRIPT_ESCAPES

register = template.Library()
CURRENCY = "IRR"


def _enabled(context) -> bool:
    return bool(getattr(context.get("site_settings"), "ga_measurement_id", ""))


def _script(name: str, params: dict, once_key: str = "") -> str:
    payload = json.dumps(params, ensure_ascii=False).translate(_SCRIPT_ESCAPES)
    call = f"window.shopTrack&&window.shopTrack({json.dumps(name)},{payload});"
    if once_key:  # e.g. a purchase page reloaded later must not count the sale twice
        key = json.dumps(once_key)
        call = f"try{{if(!sessionStorage.getItem({key})){{sessionStorage.setItem({key},'1');{call}}}}}catch(e){{{call}}}"
    return mark_safe(f"<script>{call}</script>")


def _product_item(product, variant=None, quantity=1) -> dict:
    offer = variant or product
    item = {
        "item_id": (variant.sku or f"{product.pk}-{variant.pk}") if variant else str(product.pk),
        "item_name": product.name,
        "price": offer.effective_price * 10,
        "quantity": quantity,
    }
    if variant:
        item["item_variant"] = variant.label
    if product.brand_id:
        item["item_brand"] = product.brand.name
    if product.category_id:
        item["item_category"] = product.category.name
    return item


@register.simple_tag(takes_context=True)
def ga_view_item(context, product, variant=None):
    if not _enabled(context):
        return ""
    item = _product_item(product, variant)
    return _script("view_item", {"currency": CURRENCY, "value": item["price"], "items": [item]})


@register.simple_tag(takes_context=True)
def ga_add_to_cart(context, product, variant=None, quantity=1):
    if not _enabled(context) or product is None:
        return ""
    item = _product_item(product, variant, int(quantity))
    return _script("add_to_cart", {"currency": CURRENCY, "value": item["price"] * item["quantity"], "items": [item]})


@register.simple_tag(takes_context=True)
def ga_begin_checkout(context, summary):
    if not _enabled(context) or not summary.get("items"):
        return ""
    items = [_product_item(row["product"], row["variant"], row["item"].quantity) for row in summary["items"]]
    return _script("begin_checkout", {"currency": CURRENCY, "value": summary["subtotal"] * 10, "items": items})


@register.simple_tag(takes_context=True)
def ga_purchase(context, order):
    if not _enabled(context):
        return ""
    items = []
    for line in order.items.all():
        item = {
            "item_id": str(line.product_id or f"line-{line.pk}"),
            "item_name": line.product_name,
            "price": line.unit_price * 10,
            "quantity": line.quantity,
        }
        if line.variant_label:
            item["item_variant"] = line.variant_label
        items.append(item)
    params = {
        "transaction_id": order.order_number,
        "currency": CURRENCY,
        "value": order.total * 10,
        "shipping": order.shipping_cost * 10,
        "items": items,
    }
    if order.coupon_code:
        params["coupon"] = order.coupon_code
    return _script("purchase", params, once_key=f"ga-purchase-{order.order_number}")
