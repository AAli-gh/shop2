import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from apps.catalog import importer
from apps.catalog.stock import sync_variant_totals
from apps.common.admin_jalali import jalali_column

from apps.catalog.models import (
    Attribute,
    Banner,
    Brand,
    Category,
    Product,
    ProductAttributeValue,
    ProductImage,
    ProductVariant,
    RestockNotification,
    SearchTerm,
)


XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx_response(content: bytes, filename: str) -> HttpResponse:
    response = HttpResponse(content, content_type=XLSX_TYPE)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


class _nothing:
    """Context manager standing in for the optional ZIP file."""

    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    fields = ("color_name", "color_hex", "option", "sku", "price", "sale_price", "stock", "image", "is_active", "sort_order")
    verbose_name_plural = "تنوع‌ها (رنگ / ظرفیت) — اگر محصول تنوع دارد، قیمت و موجودی فقط از همین‌جا تعیین می‌شود"


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 3


class ProductAttributeValueInline(admin.TabularInline):
    model = ProductAttributeValue
    extra = 0
    autocomplete_fields = ("attribute",)


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "country", "is_active")
    list_filter = ("is_active", "country")
    search_fields = ("name",)
    prepopulated_fields = {}


@admin.register(Attribute)
class AttributeAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "data_type", "unit", "is_filterable", "sort_order")
    list_filter = ("category", "data_type", "is_filterable")
    search_fields = ("name",)
    autocomplete_fields = ("category",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "is_active", "attribute_count")
    list_filter = ("is_active",)
    search_fields = ("name",)
    prepopulated_fields = {}

    @admin.display(description="مشخصات فنی")
    def attribute_count(self, obj):
        return obj.attributes.count()


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    fieldsets = (
        (None, {"fields": ("name", "category", "brand", "description", "image", "video_url")}),
        ("قیمت و تخفیف", {"fields": ("price", "sale_price", "sale_starts_at", "sale_ends_at", "cost_price", "is_featured"),
                          "description": "با پر کردن «پایان تخفیف»، کالا با شمارش معکوس در بخش «شگفت‌انگیز امروز» صفحه اول نمایش داده می‌شود."}),
        ("اقساط", {"fields": ("installment_months", "installment_down_payment"),
                   "classes": ("collapse",), "description": "برای فروش قسطی — ماه‌ها: ۰ = بدون قسط"}),
        ("مشخصات کالا", {"fields": ("country", "warranty", "energy_class", "weight_kg", "requires_install"),
                         "classes": ("collapse",)}),
        ("موجودی", {"fields": ("stock", "sold_count", "is_active")}),
        ("تاریخ‌ها", {"fields": ("created_jalali", "updated_jalali")}),
    )
    list_display = ("name", "brand", "category", "price", "sale_price", "sale_ends_jalali", "stock", "variant_count",
                    "sold_count", "is_featured", "is_active")
    list_filter = ("is_active", "is_featured", "brand", "category", "requires_install")
    search_fields = ("name", "description")
    list_editable = ("price", "sale_price", "stock", "is_featured", "is_active")
    autocomplete_fields = ("brand", "category")
    # Django 6 default; also keeps the list-editable changelist form free of the deprecation warning
    formfield_overrides = {models.URLField: {"assume_scheme": "https"}}
    inlines = [ProductVariantInline, ProductImageInline, ProductAttributeValueInline]
    readonly_fields = ("created_jalali", "updated_jalali", "sold_count")
    actions = ["activate_selected", "deactivate_selected", "export_excel"]

    created_jalali = jalali_column("created_at", "تاریخ ثبت")
    updated_jalali = jalali_column("updated_at", "آخرین تغییر")
    sale_ends_jalali = jalali_column("sale_ends_at", "پایان تخفیف")

    @admin.action(description="فعال‌سازی محصولات انتخاب‌شده")
    def activate_selected(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} محصول فعال شد.")

    @admin.action(description="غیرفعال‌سازی محصولات انتخاب‌شده")
    def deactivate_selected(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} محصول غیرفعال شد.")

    @admin.action(description="خروجی Excel (قابل ویرایش و ورود دوباره)")
    def export_excel(self, request, queryset):
        return _xlsx_response(importer.build_workbook(queryset), f"products-{datetime.now():%Y%m%d}.xlsx")

    # ------------------------------------------------------------ bulk import
    IMPORT_SESSION_KEY = "product_import"
    IMPORT_MAX_DATA_BYTES = 5 * 1024 * 1024
    IMPORT_MAX_ZIP_BYTES = 25 * 1024 * 1024

    def get_urls(self):
        view = self.admin_site.admin_view
        return [
            path("import/", view(self.import_view), name="catalog_product_import"),
            path("import/template/", view(self.import_template_view), name="catalog_product_import_template"),
        ] + super().get_urls()

    def _check_import_permission(self, request):
        if not (self.has_add_permission(request) and self.has_change_permission(request)):
            raise PermissionDenied

    def import_template_view(self, request):
        self._check_import_permission(request)
        return _xlsx_response(importer.build_workbook(), "product-import-template.xlsx")

    def import_view(self, request):
        """Upload → preview (nothing saved) → confirm. Files wait in the temp folder between the two steps."""
        self._check_import_permission(request)
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "ورود گروهی محصولات",
            "columns": importer.COLUMNS,
            "max_rows": importer.MAX_ROWS,
        }
        pending = request.session.get(self.IMPORT_SESSION_KEY)

        if request.method == "POST" and request.POST.get("step") == "confirm":
            if not pending or request.POST.get("token") != pending["token"]:
                messages.error(request, "این پیش‌نمایش منقضی شده است؛ فایل را دوباره بارگذاری کنید.")
                return redirect("admin:catalog_product_import")
            report = self._run_pending_import(pending, commit=True)
            del request.session[self.IMPORT_SESSION_KEY]
            if report is None:
                messages.error(request, "فایل بارگذاری‌شده دیگر در دسترس نیست؛ دوباره بارگذاری کنید.")
                return redirect("admin:catalog_product_import")
            from apps.common import shoplog

            shoplog.product_imported(report.created, report.updated, len(report.errors), pending["filename"])
            text = f"ورود محصولات انجام شد: {report.created} محصول جدید، {report.updated} به‌روزرسانی."
            if report.variants_created or report.variants_updated:
                text += f" تنوع‌ها: {report.variants_created} جدید، {report.variants_updated} به‌روزرسانی."
            if report.errors:
                text += f" {len(report.errors)} ردیف به دلیل خطا وارد نشد."
            messages.success(request, text)
            return redirect("admin:catalog_product_changelist")

        if request.method == "POST":
            self._discard_pending(pending)
            request.session.pop(self.IMPORT_SESSION_KEY, None)
            data_file, zip_file = request.FILES.get("file"), request.FILES.get("images")
            error = self._upload_error(data_file, zip_file)
            if error:
                context["upload_error"] = error
                return TemplateResponse(request, "admin/catalog/product/import.html", context)
            pending = self._store_upload(data_file, zip_file)
            report = self._run_pending_import(pending, commit=False)
            if isinstance(report, str):
                self._discard_pending(pending)
                context["upload_error"] = report
                return TemplateResponse(request, "admin/catalog/product/import.html", context)
            request.session[self.IMPORT_SESSION_KEY] = pending
            context.update(report=report, token=pending["token"], filename=pending["filename"],
                           zip_name=pending.get("zip_name", ""))
        return TemplateResponse(request, "admin/catalog/product/import.html", context)

    def _upload_error(self, data_file, zip_file):
        if data_file is None:
            return "فایل Excel یا CSV محصولات را انتخاب کنید."
        if not data_file.name.lower().endswith((".xlsx", ".xlsm", ".csv")):
            return "فایل محصولات باید Excel (xlsx) یا CSV باشد."
        if data_file.size > self.IMPORT_MAX_DATA_BYTES:
            return "فایل محصولات بزرگ‌تر از ۵ مگابایت است."
        if zip_file is not None:
            if not zip_file.name.lower().endswith(".zip"):
                return "تصاویر باید در یک فایل ZIP باشند."
            if zip_file.size > self.IMPORT_MAX_ZIP_BYTES:
                return "فایل ZIP تصاویر بزرگ‌تر از ۲۵ مگابایت است؛ آن را در چند نوبت وارد کنید."
        return ""

    @staticmethod
    def _import_dir() -> Path:
        folder = Path(tempfile.gettempdir()) / "shop2-imports"
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.iterdir():  # uploads that were previewed but never confirmed
            if old.stat().st_mtime < time.time() - 24 * 3600:
                old.unlink(missing_ok=True)
        return folder

    def _store_upload(self, data_file, zip_file) -> dict:
        folder = self._import_dir()
        token = uuid.uuid4().hex
        suffix = Path(data_file.name).suffix.lower()
        pending = {"token": token, "filename": data_file.name, "data_path": str(folder / f"{token}{suffix}")}
        with open(pending["data_path"], "wb") as fh:
            for chunk in data_file.chunks():
                fh.write(chunk)
        if zip_file is not None:
            pending["zip_name"] = zip_file.name
            pending["zip_path"] = str(folder / f"{token}.zip")
            with open(pending["zip_path"], "wb") as fh:
                for chunk in zip_file.chunks():
                    fh.write(chunk)
        return pending

    @staticmethod
    def _discard_pending(pending):
        for key in ("data_path", "zip_path"):
            if pending and pending.get(key):
                Path(pending[key]).unlink(missing_ok=True)

    def _run_pending_import(self, pending, *, commit):
        """The report; a message string when the file as a whole is unusable; None when the upload is gone."""
        data_path = Path(pending["data_path"])
        zip_path = Path(pending["zip_path"]) if pending.get("zip_path") else None
        if not data_path.exists() or (zip_path and not zip_path.exists()):
            return None
        try:
            with open(data_path, "rb") as data, (open(zip_path, "rb") if zip_path else _nothing()) as images:
                return importer.run_import(data, pending["filename"], images, commit=commit)
        except importer.ImportFileError as exc:
            return str(exc)
        finally:
            if commit:
                self._discard_pending(pending)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        if self.has_add_permission(request) and self.has_change_permission(request):
            extra_context["import_url"] = reverse("admin:catalog_product_import")
        return super().changelist_view(request, extra_context)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            active_variant_count=Count("variants", filter=Q(variants__is_active=True))
        )

    @admin.display(description="تنوع", ordering="active_variant_count")
    def variant_count(self, obj):
        return getattr(obj, "active_variant_count", 0) or "—"

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj is not None and obj.variants.exists():
            fields = (*fields, "price", "sale_price", "stock")  # mirrored from the variants
        return fields

    def save_model(self, request, obj, form, change):
        obj._was_out_of_stock = change and Product.objects.filter(pk=obj.pk, stock=0).exists()
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        product = form.instance
        # variants edited inline decide price and stock; this also undoes list-editable edits of those
        sync_variant_totals(product.pk)
        product.refresh_from_db(fields=["price", "sale_price", "stock"])
        if getattr(product, "_was_out_of_stock", False) and product.stock > 0:
            from apps.orders.emails import restock_available

            restock_available(product)


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ("thumb", "title", "link", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")

    @admin.display(description="تصویر")
    def thumb(self, obj):
        from django.utils.html import format_html

        if obj.image:
            return format_html('<img src="{}" style="height:36px;border-radius:6px">', obj.image.url)
        return "—"


@admin.register(RestockNotification)
class RestockNotificationAdmin(admin.ModelAdmin):
    list_display = ("product", "email", "notified", "created_jalali")
    list_filter = ("notified",)
    search_fields = ("email", "product__name")

    created_jalali = jalali_column("created_at", "تاریخ درخواست")


@admin.register(SearchTerm)
class SearchTermAdmin(admin.ModelAdmin):
    """What customers look for: popular terms, and the ones that found nothing (products to add?)."""

    list_display = ("display", "count", "results_count", "is_hidden", "last_searched_jalali")
    list_editable = ("is_hidden",)
    list_filter = ("is_hidden",)
    search_fields = ("display", "term")
    readonly_fields = ("term", "display", "count", "results_count", "last_searched_jalali")
    fields = ("display", "term", "count", "results_count", "last_searched_jalali", "is_hidden")

    last_searched_jalali = jalali_column("last_searched_at", "آخرین جستجو")

    def has_add_permission(self, request):
        return False
