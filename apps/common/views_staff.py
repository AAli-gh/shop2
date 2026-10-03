from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.common.dashboard import sales_stats


def staff_member_required(view):
    """Staff pages share the admin's sign-in, including its SMS code step (apps.accounts.admin_site)."""
    return admin.site.admin_view(view)


@staff_member_required
def dashboard(request):
    stats = sales_stats()
    max_total = max((row["total"] for row in stats["series"]), default=0)
    return render(
        request,
        "pages/dashboard.html",
        {"stats": stats, "max_total_val": max_total or 1},
    )


@staff_member_required
def logs_view(request):
    """Tail of logs/shop.log (and error.log) for staff; ?n=200 controls lines."""
    from pathlib import Path

    from django.conf import settings

    try:
        n = min(max(int(request.GET.get("n", 200)), 1), 1000)
    except (TypeError, ValueError):
        n = 200
    which = request.GET.get("file", "shop")
    name = "error.log" if which == "error" else "shop.log"
    path = Path(settings.LOG_DIR) / name
    lines = []
    if path.exists():
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()[-n:]
        except OSError:
            lines = []
    return render(
        request,
        "pages/logs.html",
        {"log_lines": [l.rstrip("\n") for l in reversed(lines)], "log_name": name},
    )


@staff_member_required
def logs_download(request):
    """Download the selected log file."""
    from pathlib import Path

    from django.conf import settings

    which = request.GET.get("file", "shop")
    name = "error.log" if which == "error" else "shop.log"
    path = Path(settings.LOG_DIR) / name
    if not path.exists():
        return HttpResponse("", content_type="text/plain; charset=utf-8")
    content = path.read_text(encoding="utf-8", errors="replace")
    response = HttpResponse(content, content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{name}"'
    return response


def _require(request, perm: str) -> None:
    if not request.user.has_perm(perm):
        raise PermissionDenied


@staff_member_required
def stock_forecast_view(request):
    """Which products run out soon at the current sales speed, and how many to reorder."""
    from apps.catalog.forecast import stock_forecast

    _require(request, "catalog.view_product")
    show_all = request.GET.get("all") == "1"
    return render(request, "pages/stock_forecast.html", {"forecast": stock_forecast(include_ok=show_all), "show_all": show_all})


@staff_member_required
def missed_searches_view(request):
    """Searches that found nothing; staff can map a word to the shop's own (synonym) or dismiss it."""
    from apps.catalog.models import SearchSynonym, SearchTerm
    from apps.catalog.search_report import missed_searches
    from apps.common.text import normalize_search

    _require(request, "catalog.view_searchterm")
    if request.method == "POST":
        term = get_object_or_404(SearchTerm, pk=request.POST.get("term_id") or 0)
        if request.POST.get("action") == "dismiss":
            _require(request, "catalog.change_searchterm")
            SearchTerm.objects.filter(pk=term.pk).update(dismissed=True)
            messages.success(request, f"«{term.display}» از این گزارش کنار گذاشته شد.")
        else:
            _require(request, "catalog.add_searchsynonym")
            replacement = normalize_search(request.POST.get("replacement", ""))[:100]
            if not replacement:
                messages.error(request, "کلمه جایگزین را وارد کنید.")
            else:
                SearchSynonym.objects.update_or_create(term=term.term, defaults={"replacement": replacement})
                messages.success(request, f"از این به بعد جستجوی «{term.display}» دنبال «{replacement}» می‌گردد.")
        return redirect("common:missed_searches")
    return render(request, "pages/missed_searches.html", {"rows": missed_searches()})


@staff_member_required
def customer_segments_view(request):
    """Customers grouped by buying habit, and how the win-back campaign is doing."""
    from apps.crm.segments import segments_report
    from apps.crm.winback import campaign_stats

    _require(request, "accounts.view_user")
    return render(request, "pages/customer_segments.html", {
        "report": segments_report(segment=request.GET.get("segment", "")),
        "campaign": campaign_stats(),
    })
