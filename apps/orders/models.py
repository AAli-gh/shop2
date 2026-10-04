from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Order(models.Model):
    class PaymentTerms(models.TextChoices):
        CASH = "cash", "نقدی هنگام تحویل"
        CHEQUE = "cheque", "چک"
        CREDIT = "credit", "اعتباری (حساب)"

    class Status(models.TextChoices):
        AWAITING_APPROVAL = "approval", "در انتظار تأیید شرکت"  # placed by a sales rep, paid on account
        PENDING_PAYMENT = "pending_payment", "در انتظار پرداخت"
        PAID = "paid", "پرداخت‌شده"
        PROCESSING = "processing", "در حال پردازش"
        SHIPPED = "shipped", "ارسال شد"
        DELIVERED = "delivered", "تحویل شد"
        CANCELLED = "cancelled", "لغو شد"

    order_number = models.CharField(_("order number"), max_length=20, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="orders", on_delete=models.PROTECT,
        verbose_name=_("user"),
    )
    status = models.CharField(
        _("status"), max_length=20, choices=Status.choices,
        default=Status.PENDING_PAYMENT, db_index=True,
    )
    items_subtotal = models.BigIntegerField(_("items subtotal"), default=0)
    discount_amount = models.BigIntegerField(_("discount amount"), default=0)
    shipping_cost = models.BigIntegerField(_("shipping cost"), default=0)
    total = models.BigIntegerField(_("total"), default=0)
    coupon = models.ForeignKey(
        "discounts.Coupon", null=True, blank=True, on_delete=models.SET_NULL,
        verbose_name=_("coupon"),
    )
    coupon_code = models.CharField(_("coupon code"), max_length=40, blank=True)
    payment_ref = models.CharField(_("payment reference"), max_length=60, blank=True)
    tracking_code = models.CharField(
        _("tracking code"), max_length=60, blank=True,
        help_text=_("کد رهگیری مرسوله پستی"),
    )
    shipping_note = models.CharField(
        _("shipping note"), max_length=200, blank=True,
        help_text=_("مثلاً نام باربری یا توضیح ارسال"),
    )
    shipping_method = models.ForeignKey(
        "orders.ShippingMethod", null=True, blank=True, on_delete=models.SET_NULL,
        verbose_name=_("shipping method"),
    )
    install_requested = models.BooleanField(_("install requested"), default=False)
    install_cost = models.BigIntegerField(_("install cost"), default=0)
    install_date = models.CharField(_("install date"), max_length=30, blank=True, help_text="ترجیح زمانی نصب")
    wallet_used = models.BigIntegerField(_("paid from wallet"), default=0, help_text=_("مبلغ کسرشده از کیف پول"))
    delivered_at = models.DateTimeField(_("delivered at"), null=True, blank=True)  # starts the return window
    # orders a sales rep placed for one of their shops (apps.reps); `user` is then the rep's account
    sales_rep = models.ForeignKey(
        "reps.SalesRep", null=True, blank=True, related_name="orders", on_delete=models.PROTECT,
        verbose_name=_("sales rep"),
    )
    rep_customer = models.ForeignKey(
        "reps.RepCustomer", null=True, blank=True, related_name="orders", on_delete=models.PROTECT,
        verbose_name=_("rep customer"),
    )
    payment_terms = models.CharField(_("payment terms"), max_length=10, choices=PaymentTerms.choices, blank=True)
    # set by `manage.py request_reviews`, so a customer is asked for a review only once
    review_requested_at = models.DateTimeField(_("review requested at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("order")
        verbose_name_plural = _("orders")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self):
        return self.order_number

    @property
    def progress_steps(self):
        """Linear fulfilment steps for the order timeline, each marked done/current."""
        # a rep's order waits for company approval and is paid on account; a shop order is paid online
        skipped = {self.Status.CANCELLED}
        skipped |= {self.Status.PENDING_PAYMENT, self.Status.PAID} if self.sales_rep_id else {self.Status.AWAITING_APPROVAL}
        flow = [s for s in self.Status if s not in skipped]
        current = flow.index(self.status) if self.status in flow else -1
        return [
            {"label": s.label, "done": i < current, "current": i == current}
            for i, s in enumerate(flow)
        ]


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order, related_name="items", on_delete=models.CASCADE, verbose_name=_("order")
    )
    product = models.ForeignKey(
        "catalog.Product", null=True, blank=True, on_delete=models.SET_NULL,
        verbose_name=_("product"),
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant", null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_("variant"),
    )
    # includes the variant label, so invoices and emails need nothing else
    product_name = models.CharField(_("product name"), max_length=200)
    variant_label = models.CharField(_("variant"), max_length=110, blank=True)
    unit_price = models.BigIntegerField(_("unit price"))
    # what the shop paid for one unit when the order was placed, for the profit report
    unit_cost = models.BigIntegerField(_("unit cost"), null=True, blank=True)
    quantity = models.PositiveSmallIntegerField(_("quantity"))
    line_total = models.BigIntegerField(_("line total"))
    # after-sales: filled in by staff when the goods leave the warehouse
    serial_numbers = models.CharField(
        _("serial numbers"), max_length=200, blank=True, help_text="شماره سریال کالاهای این ردیف؛ چندتایی را با ، جدا کنید",
    )
    warranty_ends_at = models.DateField(_("warranty ends at"), null=True, blank=True)

    class Meta:
        verbose_name = _("order item")
        verbose_name_plural = _("order items")

    def __str__(self):
        return f"{self.product_name} x{self.quantity}"


class ShippingAddress(models.Model):
    order = models.OneToOneField(
        Order, related_name="shipping_address", on_delete=models.CASCADE,
        verbose_name=_("order"),
    )
    full_name = models.CharField(_("full name"), max_length=120)
    phone = models.CharField(_("phone number"), max_length=15)
    province = models.CharField(_("province"), max_length=60)
    city = models.CharField(_("city"), max_length=60)
    postal_code = models.CharField(_("postal code"), max_length=10)
    address_line = models.CharField(_("address"), max_length=300)

    class Meta:
        verbose_name = _("shipping address")
        verbose_name_plural = _("shipping addresses")

    def __str__(self):
        return f"{self.full_name} - {self.city}"


class OrderNote(models.Model):
    """Internal staff note on an order. Never shown to the customer."""

    order = models.ForeignKey(Order, related_name="notes", on_delete=models.CASCADE, verbose_name=_("order"))
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name=_("author"),
    )
    body = models.TextField(_("note"), max_length=2000)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("internal note")
        verbose_name_plural = _("internal notes")
        ordering = ["-created_at"]

    def __str__(self):
        return self.body[:60]


class ReturnRequest(models.Model):
    """A customer's request to send back items from a delivered order."""

    class Reason(models.TextChoices):
        DEFECTIVE = "defective", "کالا خراب یا معیوب است"
        DAMAGED = "damaged", "کالا در ارسال آسیب دیده است"
        WRONG_ITEM = "wrong_item", "کالای اشتباه ارسال شده است"
        NOT_AS_DESCRIBED = "not_as_described", "کالا با مشخصات سایت مطابقت ندارد"
        CHANGED_MIND = "changed_mind", "از خرید منصرف شده‌ام"
        OTHER = "other", "سایر"

    class Resolution(models.TextChoices):
        REFUND = "refund", "بازگشت وجه"
        REPLACE = "replace", "تعویض کالا"

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار بررسی"
        APPROVED = "approved", "تأیید شد"
        RECEIVED = "received", "کالا دریافت شد"
        COMPLETED = "completed", "انجام شد"
        REJECTED = "rejected", "رد شد"

    OPEN_STATUSES = (Status.PENDING, Status.APPROVED, Status.RECEIVED)

    order = models.ForeignKey(
        Order, related_name="return_requests", on_delete=models.CASCADE, verbose_name=_("order"),
    )
    reason = models.CharField(_("reason"), max_length=20, choices=Reason.choices)
    resolution = models.CharField(_("requested resolution"), max_length=10, choices=Resolution.choices, default=Resolution.REFUND)
    description = models.TextField(_("description"), max_length=2000)
    image = models.ImageField(_("photo"), upload_to="returns/", blank=True)
    status = models.CharField(_("status"), max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    staff_note = models.TextField(
        _("reply to customer"), blank=True, help_text="در صفحه سفارش مشتری و پیام اطلاع‌رسانی نمایش داده می‌شود",
    )
    # set once when staff complete the request
    refund_amount = models.BigIntegerField(_("refunded to wallet"), default=0, help_text=_("in Toman"))
    restocked = models.BooleanField(_("returned to stock"), default=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("return request")
        verbose_name_plural = _("return requests")
        ordering = ["-created_at"]

    def __str__(self):
        return f"مرجوعی {self.order.order_number} #{self.pk}"


class ReturnRequestItem(models.Model):
    return_request = models.ForeignKey(
        ReturnRequest, related_name="items", on_delete=models.CASCADE, verbose_name=_("return request"),
    )
    order_item = models.ForeignKey(
        OrderItem, related_name="return_items", on_delete=models.PROTECT, verbose_name=_("order item"),
    )
    quantity = models.PositiveSmallIntegerField(_("quantity"))

    class Meta:
        verbose_name = _("returned item")
        verbose_name_plural = _("returned items")
        constraints = [
            models.UniqueConstraint(fields=["return_request", "order_item"], name="unique_item_per_return"),
        ]

    def __str__(self):
        return f"{self.order_item.product_name} x{self.quantity}"


class ShippingMethod(models.Model):
    name = models.CharField(_("name"), max_length=100)
    description = models.CharField(_("description"), max_length=200, blank=True)
    price = models.BigIntegerField(_("price"), default=0, help_text=_("in Toman; 0 = free"))
    is_active = models.BooleanField(_("active"), default=True)
    sort_order = models.PositiveSmallIntegerField(_("sort order"), default=0)

    class Meta:
        verbose_name = _("shipping method")
        verbose_name_plural = _("shipping methods")
        ordering = ["sort_order", "price"]

    def __str__(self):
        return self.name
