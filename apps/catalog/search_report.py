"""«What customers searched for and didn't find» — the staff report behind /dashboard/searches/.

Each missed search is checked again against today's catalog (a product or synonym may have been
added since); one that finds something now leaves the report by itself.
"""
from datetime import timedelta

from django.utils import timezone

from apps.catalog.models import SearchTerm

WINDOW_DAYS = 90


def _missed(now=None):
    since = (now or timezone.now()) - timedelta(days=WINDOW_DAYS)
    return SearchTerm.objects.filter(results_count=0, dismissed=False, last_searched_at__gte=since)


def missed_count(now=None) -> int:
    return _missed(now).count()


def missed_searches(now=None, limit=50) -> list[dict]:
    """Most searched first: the term, how many products it finds now, and close words from the catalog."""
    from apps.catalog.search_suggest import suggest
    from apps.catalog.services import search_count

    rows = []
    for term in _missed(now).order_by("-count", "-last_searched_at")[:limit]:
        found = search_count(term.display)
        if found:
            SearchTerm.objects.filter(pk=term.pk).update(results_count=found)
        rows.append({"term": term, "found_now": found, "suggestions": [] if found else suggest(term.display)})
    return rows
