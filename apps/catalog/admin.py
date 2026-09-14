import csv
from datetime import datetime

from django.contrib import admin
from django.http import HttpResponse

from apps.common.admin_jalali import jalali_column

from apps.catalog.models import (
    Attribute,
    Banner,
    Brand,
    Category,
    Product,
    ProductAttributeValue,
    ProductImage,
    RestockNotification,
)


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
        ("قیمت و تخفیف", {"fields": ("price", "sale_price", "is_featured")}),
        ("اقساط", {"fields": ("installment_months", "installment_down_payment"),
                   "classes": ("collapse",), "description": "برای فروش قسطی — ماه‌ها: ۰ = بدون قسط"}),
        ("مشخصات کالا", {"fields": ("country", "warranty", "energy_class", "weight_kg", "requires_install"),
                         "classes": ("collapse",)}),
        ("موجودی", {"fields": ("stock", "sold_count", "is_active")}),
        ("تاریخ‌ها", {"fields": ("created_jalali", "updated_jalali")}),
    )
    list_display = ("name", "brand", "category", "price", "sale_price", "stock", "warranty", "sold_count", "is_featured", "is_active")
    list_filter = ("is_active", "is_featured", "brand", "category", "requires_install")
    search_fields = ("name", "description")
    list_editable = ("price", "sale_price", "stock", "is_featured", "is_active")
    autocomplete_fields = ("brand", "category")
    inlines = [ProductImageInline, ProductAttributeValueInline]
    readonly_fields = ("created_jalali", "updated_jalali", "sold_count")
    actions = ["activate_selected", "deactivate_selected", "export_csv"]

    created_jalali = jalali_column("created_at", "تاریخ ثبت")
    updated_jalali = jalali_column("updated_at", "آخرین تغییر")

    @admin.action(description="فعال‌سازی محصولات انتخاب‌شده")
    def activate_selected(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} محصول فعال شد.")

    @admin.action(description="غیرفعال‌سازی محصولات انتخاب‌شده")
    def deactivate_selected(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} محصول غیرفعال شد.")

    @admin.action(description="خروجی CSV محصولات")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename=products-{datetime.now():%Y%m%d}.csv'
        response.write("﻿")
        writer = csv.writer(response)
        writer.writerow(["نام", "slug", "برند", "دسته", "قیمت", "قیمت تخفیف", "موجودی", "گارانتی", "فروش", "ویترین", "فعال"])
        for p in queryset.select_related("category", "brand"):
            writer.writerow([
                p.name, p.slug, p.brand.name if p.brand else "", p.category.name, p.price,
                p.sale_price or "", p.stock, p.warranty, p.sold_count,
                "بله" if p.is_featured else "خیر", "فعال" if p.is_active else "غیرفعال",
            ])
        return response

    def save_model(self, request, obj, form, change):
        was_out_of_stock = change and Product.objects.filter(pk=obj.pk, stock=0).exists()
        super().save_model(request, obj, form, change)
        if was_out_of_stock and obj.stock > 0:
            from apps.orders.emails import restock_available

            restock_available(obj)


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
