"""What the empty search box suggests: this visitor's recent searches and the shop's popular ones.

Recent searches live in the session, so guests get them too. Popular searches are counted in
SearchTerm, once per session per term so reloading or paging a result doesn't inflate them.
Only terms that found products, were searched more than once and weren't hidden by staff are
ever shown to other visitors, since the text comes from the public.
"""
from datetime import timedelta

from django.db.models import F
from django.utils import timezone

from apps.catalog.models import SearchTerm
from apps.common.text import normalize_search

RECENT_KEY = "recent_searches"
COUNTED_KEY = "counted_searches"
RECENT_LIMIT = 6
POPULAR_LIMIT = 8
POPULAR_MIN_COUNT = 2
POPULAR_WINDOW_DAYS = 90
MAX_TERM_LENGTH = 100


def _clean(raw) -> str:
    return " ".join(str(raw or "").split())[:MAX_TERM_LENGTH]


def record_search(request, raw_query, results_count: int) -> None:
    """Remember a submitted search for this visitor and count it towards the popular list."""
    text = _clean(raw_query)
    key = normalize_search(text)
    if len(key) < 2:
        return

    recent = [q for q in request.session.get(RECENT_KEY, []) if normalize_search(q) != key]
    request.session[RECENT_KEY] = [text, *recent][:RECENT_LIMIT]

    counted = request.session.get(COUNTED_KEY, [])
    if key in counted:
        return
    request.session[COUNTED_KEY] = [*counted, key][-50:]
    now = timezone.now()
    updated = SearchTerm.objects.filter(term=key).update(
        count=F("count") + 1, results_count=results_count, display=text, last_searched_at=now,
    )
    if not updated:
        SearchTerm.objects.get_or_create(
            term=key, defaults={"display": text, "results_count": results_count, "last_searched_at": now},
        )


def recent_searches(request) -> list[str]:
    return list(request.session.get(RECENT_KEY, []))


def clear_recent(request) -> None:
    request.session.pop(RECENT_KEY, None)


def popular_searches(limit: int = POPULAR_LIMIT) -> list[str]:
    since = timezone.now() - timedelta(days=POPULAR_WINDOW_DAYS)
    terms = SearchTerm.objects.filter(
        is_hidden=False, results_count__gt=0, count__gte=POPULAR_MIN_COUNT, last_searched_at__gte=since,
    ).order_by("-count", "-last_searched_at")[:limit]
    return [term.display for term in terms]
