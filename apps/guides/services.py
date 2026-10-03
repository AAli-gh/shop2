"""Buying guide: score a category's products against the customer's answers.

Every chosen option with a rule is checked against each product. A product failing a required rule
is dropped; every rule it meets adds a point and a reason («ظرفیت: ۶۵۰ لیتر»), every one it misses
is listed too, so the customer sees why a product ranks where it does. Ties go to products in
stock, then best sellers, then the cheaper one. When the required rules leave nothing, the closest
products are shown instead, all rules treated as preferences, and the page says so.
"""
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.db.models import Prefetch, Q

from apps.common.text import normalize_search

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


@dataclass
class Match:
    product: object
    score: int = 0
    rules: int = 0
    reasons: list = field(default_factory=list)
    misses: list = field(default_factory=list)

    @property
    def percent(self) -> int:
        return round(self.score * 100 / self.rules) if self.rules else 100


def spec_number(value) -> Decimal | None:
    """A spec's numeric value: the number field, or the first number written in its text («۶۵۰ لیتر» → 650)."""
    if value.value_number is not None:
        return value.value_number
    found = _NUMBER.search(normalize_search(value.value_text))
    if not found:
        return None
    try:
        return Decimal(found.group())
    except InvalidOperation:
        return None


def _format(number: Decimal) -> str:
    return f"{number:,.0f}" if number == number.to_integral_value() else f"{number:,}"


def check(answer, product, specs: dict) -> tuple[bool, str]:
    """(does the product meet this option's rule, the reason to show)."""
    ok, reason = True, answer.reason
    if answer.attribute_id:
        value = specs.get(answer.attribute_id)
        if value is None:
            return False, f"{answer.attribute.name} نامشخص"
        if answer.min_value is not None or answer.max_value is not None:
            number = spec_number(value)
            ok = number is not None and (
                (answer.min_value is None or number >= answer.min_value)
                and (answer.max_value is None or number <= answer.max_value)
            )
        if ok and answer.text_contains:
            ok = normalize_search(answer.text_contains) in normalize_search(value.display())
        reason = reason or f"{answer.attribute.name}: {value.display()}"
    if answer.price_min is not None or answer.price_max is not None:
        price = product.effective_price
        ok = ok and (answer.price_min is None or price >= answer.price_min) and (
            answer.price_max is None or price <= answer.price_max
        )
        if not answer.attribute_id:
            reason = reason or f"قیمت {price:,} تومان"
    return ok, reason


def chosen_answers(guide, params) -> list:
    """The options picked on the form (?q<question id>=<option id>), only from this guide."""
    from apps.guides.models import GuideAnswer

    ids = []
    for question in guide.questions.all():
        raw = params.get(f"q{question.pk}", "")
        if raw.isdigit():
            ids.append(int(raw))
    return list(
        GuideAnswer.objects.filter(pk__in=ids, question__guide=guide)
        .select_related("attribute", "question").order_by("question__sort_order", "question__pk")
    )


def _candidates(guide):
    from apps.catalog.models import ProductAttributeValue
    from apps.catalog.services import _active_qs

    category = guide.category
    return (
        _active_qs()
        .filter(Q(category=category) | Q(category__parent=category))
        .prefetch_related(Prefetch("attributes", queryset=ProductAttributeValue.objects.select_related("attribute")))
    )


def recommend(guide, answers, limit=6) -> dict:
    rules = [answer for answer in answers if answer.has_rule]
    products = list(_candidates(guide))

    def score(relaxed: bool):
        results = []
        for product in products:
            specs = {value.attribute_id: value for value in product.attributes.all()}
            match = Match(product=product, rules=len(rules))
            dropped = False
            for answer in rules:
                ok, reason = check(answer, product, specs)
                if ok:
                    match.score += 1
                    match.reasons.append(reason)
                elif answer.is_required and not relaxed:
                    dropped = True
                    break
                else:
                    match.misses.append(answer.label)
            if not dropped:
                results.append(match)
        results.sort(key=lambda m: (-m.score, not m.product.in_stock, -m.product.sold_count, m.product.effective_price))
        return results

    results = score(relaxed=False)
    relaxed = bool(products) and not results
    if relaxed:
        results = score(relaxed=True)
    return {"matches": results[:limit], "relaxed": relaxed, "total": len(results)}
