from django import template

from apps.common.thumbnails import thumbnail_url

register = template.Library()


@register.filter
def thumb(image, width=400):
    """{{ product.image|thumb:400 }} — URL of a WebP copy at most 400px wide (apps.common.thumbnails)."""
    return thumbnail_url(image, int(width))
