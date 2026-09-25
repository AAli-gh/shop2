from functools import cached_property

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.common.text import normalize_search


def refresh_search_text(products) -> None:
    """Rebuild the folded search copy for products, e.g. after their brand or category is renamed."""
    batch = []
    for product in products.select_related("brand", "category"):
        product.search_text = product.build_search_text()
        batch.append(product)
    Product.objects.bulk_update(batch, ["search_text"], batch_size=200)


class Brand(models.Model):
    name = models.CharField(_("name"), max_length=120)
    slug = models.SlugField(_("slug"), max_length=120, unique=True, allow_unicode=True)
    country = models.CharField(_("country"), max_length=60, blank=True)
    logo = models.ImageField(_("logo"), upload_to="brands/", blank=True)
    description = models.TextField(_("description"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("brand")
        verbose_name_plural = _("brands")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)
        refresh_search_text(self.products.all())

    def get_absolute_url(self):
        return reverse("catalog:brand", kwargs={"brand_slug": self.slug})


class Category(models.Model):
    name = models.CharField(_("name"), max_length=120)
    slug = models.SlugField(_("slug"), max_length=120, unique=True, allow_unicode=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, related_name="children",
        on_delete=models.CASCADE, verbose_name=_("parent"),
    )
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("category")
        verbose_name_plural = _("categories")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)
        refresh_search_text(self.products.all())

    def get_absolute_url(self):
        return reverse("catalog:category", kwargs={"category_slug": self.slug})


class Attribute(models.Model):
    """A technical spec definition, scoped to a category (e.g. 'capacity' for fridges)."""

    class DataType(models.TextChoices):
        TEXT = "text", "متن"
        NUMBER = "number", "عدد"
        BOOL = "bool", "بله/خیر"

    category = models.ForeignKey(
        Category, related_name="attributes", on_delete=models.CASCADE, verbose_name=_("category")
    )
    name = models.CharField(_("name"), max_length=100)
    unit = models.CharField(_("unit"), max_length=30, blank=True, help_text=_("مثلاً لیتر، وات، سانتی‌متر"))
    data_type = models.CharField(_("data type"), max_length=10, choices=DataType.choices, default=DataType.TEXT)
    is_filterable = models.BooleanField(_("filterable"), default=True)
    sort_order = models.PositiveSmallIntegerField(_("sort order"), default=0)

    class Meta:
        verbose_name = _("attribute")
        verbose_name_plural = _("attributes")
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["category", "name"], name="unique_attr_per_category"),
        ]

    def __str__(self):
        return f"{self.name} ({self.category.name})"


class ProductAttributeValue(models.Model):
    product = models.ForeignKey(
        "catalog.Product", related_name="attributes", on_delete=models.CASCADE, verbose_name=_("product")
    )
    attribute = models.ForeignKey(
        Attribute, related_name="values", on_delete=models.CASCADE, verbose_name=_("attribute")
    )
    value_text = models.CharField(_("value text"), max_length=200, blank=True)
    value_number = models.DecimalField(_("value number"), max_digits=12, decimal_places=2, null=True, blank=True)
    value_bool = models.BooleanField(_("value bool"), null=True, blank=True)

    class Meta:
        verbose_name = _("product attribute value")
        verbose_name_plural = _("product attribute values")
        constraints = [
            models.UniqueConstraint(fields=["product", "attribute"], name="unique_value_per_attr"),
        ]

    def display(self):
        if self.attribute.data_type == Attribute.DataType.NUMBER and self.value_number is not None:
            num = int(self.value_number) if self.value_number == self.value_number.to_integral_value() else self.value_number
            return f"{num} {self.attribute.unit}".strip() if self.attribute.unit else str(num)
        if self.attribute.data_type == Attribute.DataType.BOOL and self.value_bool is not None:
            return "بله" if self.value_bool else "خیر"
        return self.value_text or "—"


class Product(models.Model):
    category = models.ForeignKey(
        Category, related_name="products", on_delete=models.PROTECT, verbose_name=_("category")
    )
    brand = models.ForeignKey(
        Brand, related_name="products", null=True, blank=True,
        on_delete=models.PROTECT, verbose_name=_("brand"),
    )
    name = models.CharField(_("name"), max_length=200)
    slug = models.SlugField(_("slug"), max_length=200, unique=True, allow_unicode=True)
    description = models.TextField(_("description"), blank=True)
    price = models.BigIntegerField(_("price"), help_text=_("in Toman"))
    sale_price = models.BigIntegerField(
        _("sale price"), null=True, blank=True, help_text=_("in Toman, discounted price")
    )
    # a timed discount ("شگفت‌انگیز"): outside the window the sale price is ignored
    sale_starts_at = models.DateTimeField(_("sale starts at"), null=True, blank=True, help_text="خالی = از همین حالا")
    sale_ends_at = models.DateTimeField(
        _("sale ends at"), null=True, blank=True,
        help_text="پایان تخفیف؛ با پر کردن آن، کالا با شمارش معکوس در «شگفت‌انگیز امروز» صفحه اول می‌آید. خالی = بدون مهلت",
    )
    cost_price = models.BigIntegerField(
        _("cost price"), null=True, blank=True,
        help_text="قیمت خرید به تومان؛ فقط برای گزارش سود و هرگز به مشتری نشان داده نمی‌شود",
    )
    stock = models.PositiveIntegerField(_("stock"), default=0)
    sold_count = models.PositiveIntegerField(_("sold count"), default=0)
    is_featured = models.BooleanField(_("featured"), default=False)
    is_active = models.BooleanField(_("active"), default=True)
    image = models.ImageField(_("image"), upload_to="products/", blank=True)
    video_url = models.URLField(_("video url"), blank=True, help_text="لینک ویدیو معرفی (آپارات/یوتیوب)")

    # appliance specifics
    country = models.CharField(_("country of origin"), max_length=60, blank=True)
    warranty = models.CharField(_("warranty"), max_length=150, blank=True, help_text="مثلاً ۲۴ ماه گارانتی رسمی پارس‌آوا")
    energy_class = models.CharField(_("energy class"), max_length=10, blank=True, help_text="A+ / A++ / A+++")
    weight_kg = models.DecimalField(_("weight (kg)"), max_digits=7, decimal_places=2, null=True, blank=True)
    requires_install = models.BooleanField(_("requires install"), default=False, help_text="نیاز به نصب تخصصی دارد")

    # installment
    installment_months = models.PositiveSmallIntegerField(_("installment months"), default=0, help_text="۰ = بدون قسط")
    installment_down_payment = models.BigIntegerField(
        _("installment down payment"), default=0, help_text=_("مقدم قسط به تومان")
    )

    # folded name + brand + category + description, so any keyboard's spelling matches (apps.common.text)
    search_text = models.TextField(_("search text"), blank=True, editable=False)

    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("product")
        verbose_name_plural = _("products")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_active", "category"]),
            models.Index(fields=["brand"]),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(price__gte=0), name="product_price_non_negative"),
            models.CheckConstraint(condition=Q(sale_price__lt=F("price")), name="product_sale_lt_price",
                                   violation_error_message="قیمت تخفیف‌خورده باید کمتر از قیمت اصلی باشد"),
        ]

    def __str__(self):
        return self.name

    def build_search_text(self) -> str:
        parts = [
            self.name,
            self.brand.name if self.brand_id else "",
            self.category.name if self.category_id else "",
            self.description,
        ]
        return normalize_search(" ".join(part for part in parts if part))

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        update_fields = kwargs.get("update_fields")
        if update_fields is None or {"name", "description", "brand", "category"} & set(update_fields):
            self.search_text = self.build_search_text()
            if update_fields is not None:
                kwargs["update_fields"] = {*update_fields, "search_text"}
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("catalog:detail", kwargs={"slug": self.slug})

    @property
    def in_stock(self):
        return self.stock > 0

    @cached_property
    def has_variants(self) -> bool:
        """Sold through colour/option variants (listing querysets annotate this to save a query per card)."""
        annotated = getattr(self, "has_variant_options", None)
        if annotated is not None:
            return annotated
        return self.variants.filter(is_active=True).exists()

    @property
    def sale_window_open(self) -> bool:
        """Whether a discount may apply now; a discount without dates is always on."""
        now = timezone.now()
        if self.sale_starts_at and now < self.sale_starts_at:
            return False
        return not (self.sale_ends_at and now > self.sale_ends_at)

    @property
    def on_sale(self) -> bool:
        return self.sale_price is not None and self.sale_window_open

    @property
    def flash_sale(self) -> bool:
        """A discount with a deadline, shown with a countdown."""
        return bool(self.sale_ends_at) and self.on_sale

    @property
    def effective_price(self):
        return self.sale_price if self.on_sale else self.price

    @property
    def discount_percent(self):
        if not self.on_sale or self.price <= 0:
            return 0
        return round((self.price - self.sale_price) * 100 / self.price)

    @property
    def has_installments(self):
        return self.installment_months and self.installment_months > 1

    @property
    def monthly_payment(self):
        """Per-month amount for the installment plan (0 if not installment-eligible)."""
        if not self.has_installments:
            return 0
        remaining = self.effective_price - self.installment_down_payment
        if remaining <= 0:
            return 0
        return round(remaining / self.installment_months)


class ProductVariant(models.Model):
    """One buyable version of a product — a colour and/or an option such as capacity — with its own price and stock.

    A product with active variants is sold only through them. Its own price, sale price and stock
    mirror the variants (cheapest prices, total stock; apps.catalog.stock.sync_variant_totals), so
    listings, price filters, sorting and search keep working on the product row alone.
    """

    product = models.ForeignKey(
        Product, related_name="variants", on_delete=models.CASCADE, verbose_name=_("product")
    )
    color_name = models.CharField(_("color"), max_length=40, blank=True, help_text="مثلاً سفید یا استیل")
    color_hex = models.CharField(
        _("color code"), max_length=7, blank=True, help_text="برای نمونه رنگ، مثلاً #C0C0C0",
        validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$", "کد رنگ را به شکل #C0C0C0 وارد کنید.")],
    )
    option = models.CharField(_("option"), max_length=60, blank=True, help_text="ظرفیت، سایز یا مدل؛ مثلاً ۲۴ فوت")
    sku = models.CharField(_("SKU"), max_length=60, blank=True)
    price = models.BigIntegerField(_("price"), help_text=_("in Toman"))
    sale_price = models.BigIntegerField(
        _("sale price"), null=True, blank=True, help_text=_("in Toman, discounted price")
    )
    stock = models.PositiveIntegerField(_("stock"), default=0)
    image = models.ImageField(_("image"), upload_to="products/variants/", blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    sort_order = models.PositiveSmallIntegerField(_("sort order"), default=0)

    class Meta:
        verbose_name = _("product variant")
        verbose_name_plural = _("product variants")
        ordering = ["sort_order", "pk"]
        constraints = [
            models.CheckConstraint(condition=Q(price__gte=0), name="variant_price_non_negative"),
            models.CheckConstraint(condition=Q(sale_price__lt=F("price")), name="variant_sale_lt_price",
                                   violation_error_message="قیمت تخفیف‌خورده باید کمتر از قیمت اصلی باشد"),
            models.CheckConstraint(condition=~Q(color_name="") | ~Q(option=""), name="variant_has_label",
                                   violation_error_message="رنگ یا گزینه (ظرفیت/مدل) را وارد کنید"),
            models.UniqueConstraint(fields=["product", "color_name", "option"], name="unique_variant_per_product",
                                    violation_error_message="این ترکیب رنگ و گزینه برای این محصول تکراری است"),
        ]

    def __str__(self):
        return self.label

    @property
    def label(self) -> str:
        return " · ".join(part for part in (self.color_name, self.option) if part)

    @property
    def in_stock(self):
        return self.stock > 0

    @property
    def on_sale(self) -> bool:
        # the product's sale window gates its variants' discounts too
        return self.sale_price is not None and self.product.sale_window_open

    @property
    def effective_price(self):
        return self.sale_price if self.on_sale else self.price

    @property
    def discount_percent(self):
        if not self.on_sale or self.price <= 0:
            return 0
        return round((self.price - self.sale_price) * 100 / self.price)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from apps.catalog.stock import sync_variant_totals

        sync_variant_totals(self.product_id)

    def delete(self, *args, **kwargs):
        product_id = self.product_id
        result = super().delete(*args, **kwargs)
        from apps.catalog.stock import sync_variant_totals

        sync_variant_totals(product_id)
        return result


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product, related_name="images", on_delete=models.CASCADE, verbose_name=_("product")
    )
    image = models.ImageField(_("image"), upload_to="products/gallery/")
    alt = models.CharField(_("alt text"), max_length=150, blank=True)
    sort_order = models.PositiveSmallIntegerField(_("sort order"), default=0)

    class Meta:
        verbose_name = _("product image")
        verbose_name_plural = _("product images")
        ordering = ["sort_order"]


class Banner(models.Model):
    title = models.CharField(_("title"), max_length=120)
    subtitle = models.CharField(_("subtitle"), max_length=200, blank=True)
    image = models.ImageField(_("image"), upload_to="banners/")
    link = models.CharField(_("link"), max_length=300, blank=True)
    sort_order = models.PositiveSmallIntegerField(_("sort order"), default=0)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("banner")
        verbose_name_plural = _("banners")
        ordering = ["sort_order"]


class RestockNotification(models.Model):
    product = models.ForeignKey(
        Product, related_name="restock_requests", on_delete=models.CASCADE,
        verbose_name=_("product"),
    )
    email = models.EmailField(_("email"))
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    notified = models.BooleanField(_("notified"), default=False)

    class Meta:
        verbose_name = _("restock notification")
        verbose_name_plural = _("restock notifications")
        constraints = [
            models.UniqueConstraint(fields=["product", "email"], name="unique_restock_request"),
        ]


class PriceAlert(models.Model):
    """A customer following a product's price; notified once it is cheaper than when they subscribed."""

    product = models.ForeignKey(
        Product, related_name="price_alerts", on_delete=models.CASCADE, verbose_name=_("product"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="price_alerts", on_delete=models.CASCADE, verbose_name=_("user"),
    )
    price_at_signup = models.BigIntegerField(_("price at signup"), help_text=_("in Toman"))
    notified_at = models.DateTimeField(_("notified at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("price alert")
        verbose_name_plural = _("price alerts")
        constraints = [
            models.UniqueConstraint(fields=["product", "user"], name="unique_price_alert"),
        ]

    def __str__(self):
        return f"{self.user} → {self.product}"


class SearchTerm(models.Model):
    """A search submitted on the shop, counted once per visitor session (apps.catalog.search_history)."""

    term = models.CharField(_("term"), max_length=100, unique=True, help_text="شکل یکسان‌سازی‌شده برای شمارش")
    display = models.CharField(_("search text"), max_length=100)
    count = models.PositiveIntegerField(_("search count"), default=1, db_index=True)
    results_count = models.PositiveIntegerField(_("results count"), default=0)
    last_searched_at = models.DateTimeField(_("last searched at"), db_index=True)
    is_hidden = models.BooleanField(
        _("hidden"), default=False,
        help_text="از فهرست «جستجوهای پرطرفدار» حذف شود (مثلاً عبارت نامناسب یا تبلیغاتی).",
    )

    class Meta:
        verbose_name = _("search term")
        verbose_name_plural = _("search terms")
        ordering = ["-count"]

    def __str__(self):
        return self.display
