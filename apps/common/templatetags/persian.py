import jdatetime
from django import template
from django.utils import timezone

register = template.Library()

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


@register.filter
def fa_digits(value):
    return str(value).translate(_FA_DIGITS)


@register.filter
def absval(value):
    try:
        return abs(int(value))
    except (TypeError, ValueError):
        return value


@register.filter
def jalali(value, fmt="%Y/%m/%d"):
    if not value:
        return ""
    local = timezone.localtime(value)
    return jdatetime.datetime.fromgregorian(datetime=local).strftime(fmt)


@register.filter
def toman(value):
    if value is None:
        return ""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{value:,} تومان"


@register.filter
def price(value):
    """Integer with thousands separators and no unit (intcomma is a no-op under the fa locale)."""
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "" if value is None else str(value)


@register.filter
def num_words(value):
    """Integer in Persian words («یک میلیون و دویست هزار»)."""
    from apps.common.numwords import number_to_words

    try:
        return number_to_words(int(value))
    except (TypeError, ValueError):
        return ""


@register.filter
def qa_paragraph(paragraph):
    """Render a paragraph whose first line is a question (bold), rest is the answer."""
    lines = [l.strip() for l in paragraph.splitlines() if l.strip()]
    if not lines:
        return ""
    from django.utils.html import escape, format_html

    q = format_html("<strong class='block mb-1'>{}</strong>", lines[0])
    a = "<br>".join(escape(l) for l in lines[1:]) if len(lines) > 1 else ""
    return format_html("{}", q + a)
