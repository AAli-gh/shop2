from django.contrib import admin
from django.http import HttpResponse
from django.shortcuts import render

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

    n = min(int(request.GET.get("n", 200)), 1000)
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
