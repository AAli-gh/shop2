"""Search synonyms: words customers use that the shop's product names don't (apps.catalog.models.SearchSynonym).

A query that is a known term as a whole is replaced outright ("ماشین ظرف" → "ظرفشویی"); otherwise each
word that is a term is swapped on its own. Everything is compared after search folding.
"""
from django.core.cache import cache

from apps.common.text import normalize_search

CACHE_KEY = "search_synonyms"
CACHE_SECONDS = 10 * 60


def synonym_map() -> dict[str, str]:
    words = cache.get(CACHE_KEY)
    if words is None:
        from apps.catalog.models import SearchSynonym

        words = dict(SearchSynonym.objects.values_list("term", "replacement"))
        cache.set(CACHE_KEY, words, CACHE_SECONDS)
    return words


def forget() -> None:
    cache.delete(CACHE_KEY)


def expand(query) -> str:
    """The folded query with synonyms applied."""
    folded = normalize_search(query)
    words = synonym_map()
    if not words or not folded:
        return folded
    if folded in words:
        return words[folded]
    return " ".join(words.get(word, word) for word in folded.split())
