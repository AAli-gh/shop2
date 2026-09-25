"""«منظورتان … بود؟» — the nearest words to a search that found nothing.

Suggestions only ever come from the shop's own vocabulary: product names and their words,
brands, categories, and earlier searches that did find something. Everything is compared
after the same folding the search itself uses, so «يخچال» and «یخچال» are one word.
"""
import difflib

from django.core.cache import cache

from apps.common.text import normalize_search

CACHE_KEY = "search_vocabulary"
CACHE_SECONDS = 10 * 60
CUTOFF = 0.62
MAX_PRODUCTS = 2000
MAX_TERMS = 200


def vocabulary() -> dict:
    """{folded phrase: the phrase as customers should see it}."""
    words = cache.get(CACHE_KEY)
    if words is not None:
        return words

    from apps.catalog.models import Brand, Category, Product, SearchTerm

    words = {}
    for name in Product.objects.filter(is_active=True).values_list("name", flat=True)[:MAX_PRODUCTS]:
        words.setdefault(normalize_search(name), name)
        for piece in name.split():  # single words survive a typo in a long name
            if len(piece) > 2:
                words.setdefault(normalize_search(piece), piece)
    for model in (Brand, Category):
        for name in model.objects.values_list("name", flat=True):
            words.setdefault(normalize_search(name), name)
    for term in SearchTerm.objects.filter(results_count__gt=0, is_hidden=False).order_by("-count")[:MAX_TERMS]:
        words.setdefault(term.term, term.display)

    cache.set(CACHE_KEY, words, CACHE_SECONDS)
    return words


def suggest(query: str, limit: int = 3) -> list[str]:
    """Up to `limit` close spellings of `query`, best first; empty when nothing is close."""
    folded = normalize_search(query)
    if len(folded) < 2:
        return []
    words = vocabulary()
    matches = difflib.get_close_matches(folded, list(words), n=limit, cutoff=CUTOFF)
    return [words[match] for match in matches if match != folded]
