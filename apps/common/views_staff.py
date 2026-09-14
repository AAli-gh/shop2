from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import redirect, render

from apps.common.dashboard import sales_stats


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
    path = Path(settings.BASE_DIR) / "logs" / name
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
    path = Path(settings.BASE_DIR) / "logs" / name
    if not path.exists():
        return HttpResponse("", content_type="text/plain; charset=utf-8")
    content = path.read_text(encoding="utf-8", errors="replace")
    response = HttpResponse(content, content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{name}"'
    return response


@staff_member_required
def import_products(request):
    summary = None
    if request.method == "POST":
        file = request.FILES.get("file")
        if not file:
            messages.error(request, "فایلی انتخاب نشده است.")
            return redirect("common:import_products")
        if not file.name.lower().endswith((".csv", ".xlsx", ".xlsm")):
            messages.error(request, "فقط فایل CSV یا Excel (xlsx) پذیرفته می‌شود.")
            return redirect("common:import_products")

        from apps.catalog.importer import import_products
        from apps.common import shoplog

        summary = import_products(file, file.name)
        shoplog.product_imported(summary["created"], summary["updated"], len(summary["errors"]), file.name)
        if summary["created"] or summary["updated"]:
            messages.success(
                request,
                f"واردات انجام شد: {summary['created']} محصول جدید، {summary['updated']} به‌روزرسانی."
                + (f" خطاها: {len(summary['errors'])}" if summary["errors"] else ""),
            )
        elif summary["errors"]:
            messages.error(request, "هیچ محصولی وارد نشد؛ خطاها در پایین صفحه آمده است.")
    return render(request, "pages/import_products.html", {"summary": summary})
