"""Jalali (Shamsi) dates in the Django admin: display columns and date-range filters.

    class OrderAdmin(admin.ModelAdmin):
        created_jalali = jalali_column("created_at", "تاریخ ثبت")
        list_display = (..., "created_jalali")
        list_filter = (jalali_date_filter("created_at", "تاریخ ثبت"),)

Date *inputs* in forms stay Gregorian (Django's widgets); displays and filters are Jalali.
"""
from datetime import date, datetime, time, timedelta

import jdatetime
from django.contrib import admin
from django.utils import timezone


def to_jalali(value, fmt: str = "%Y/%m/%d %H:%M") -> str:
    if not value:
        return "—"
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return jdatetime.datetime.fromgregorian(datetime=value).strftime(fmt)
    return jdatetime.date.fromgregorian(date=value).strftime(fmt.split(" ")[0])


def jalali_column(field_name: str, description: str, fmt: str = "%Y/%m/%d %H:%M"):
    """A ModelAdmin method (use its attribute name in list_display/readonly_fields), sortable by the field."""

    @admin.display(description=description, ordering=field_name)
    def column(model_admin, obj):
        return to_jalali(getattr(obj, field_name), fmt)

    column.__name__ = f"{field_name}_jalali"
    return column


def _aware_midnight(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.min))


def jalali_range(key: str, now: datetime | None = None) -> tuple[datetime, datetime] | None:
    """[start, end) for a named period, with months and years on the Jalali calendar."""
    today = timezone.localtime(now or timezone.now()).date()
    tomorrow = today + timedelta(days=1)
    j_today = jdatetime.date.fromgregorian(date=today)

    if key == "today":
        start, end = today, tomorrow
    elif key == "7d":
        start, end = today - timedelta(days=6), tomorrow
    elif key == "this_month":
        start, end = jdatetime.date(j_today.year, j_today.month, 1).togregorian(), tomorrow
    elif key == "last_month":
        end = jdatetime.date(j_today.year, j_today.month, 1).togregorian()
        j_last = jdatetime.date.fromgregorian(date=end - timedelta(days=1))
        start = jdatetime.date(j_last.year, j_last.month, 1).togregorian()
    elif key == "this_year":
        start, end = jdatetime.date(j_today.year, 1, 1).togregorian(), tomorrow
    else:
        return None
    return _aware_midnight(start), _aware_midnight(end)


def jalali_date_filter(field_name: str, title: str = "تاریخ"):
    """A list_filter class offering today / last 7 days / this and last Jalali month / this Jalali year."""

    class JalaliDateFilter(admin.SimpleListFilter):
        parameter_name = f"{field_name}_jalali"

        def lookups(self, request, model_admin):
            return [
                ("today", "امروز"),
                ("7d", "۷ روز اخیر"),
                ("this_month", "این ماه"),
                ("last_month", "ماه گذشته"),
                ("this_year", "امسال"),
            ]

        def queryset(self, request, queryset):
            bounds = jalali_range(self.value())
            if bounds is None:
                return queryset
            start, end = bounds
            return queryset.filter(**{f"{field_name}__gte": start, f"{field_name}__lt": end})

    JalaliDateFilter.title = title
    return JalaliDateFilter
