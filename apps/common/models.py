from django.core.cache import cache
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class SiteSettings(models.Model):
    store_name = models.CharField(_("store name"), max_length=100, default="فروشگاه من")
    shipping_flat_rate = models.BigIntegerField(
        _("flat shipping rate"), default=50_000, help_text=_("in Toman")
    )
    free_shipping_threshold = models.BigIntegerField(
        _("free shipping threshold"), null=True, blank=True, help_text=_("in Toman")
    )
    install_fee = models.BigIntegerField(
        _("install fee"), default=0, help_text=_("هزینه نصب (تومان)؛ ۰ = رایگان")
    )
    contact_phone = models.CharField(_("contact phone"), max_length=20, blank=True)
    about_text = models.TextField(_("about text"), blank=True)
    # seller details printed on invoices
    legal_name = models.CharField(
        _("seller legal name"), max_length=150, blank=True, help_text="نام شخص یا شرکت فروشنده روی فاکتور",
    )
    national_id = models.CharField(_("national ID"), max_length=20, blank=True, help_text="شناسه ملی شرکت یا کد ملی")
    economic_code = models.CharField(_("economic code"), max_length=20, blank=True)
    address = models.CharField(_("seller address"), max_length=300, blank=True)
    postal_code = models.CharField(_("seller postal code"), max_length=10, blank=True)
    trust_badges_html = models.TextField(
        _("trust badges HTML"), blank=True,
        help_text="کد HTML نماد اعتماد الکترونیکی (اینماد) و ساماندهی را دقیقاً همان‌طور که سامانه‌ها می‌دهند اینجا بچسبانید؛ "
                  "در فوتر همه صفحات نمایش داده می‌شود. فقط کد رسمی همان سامانه‌ها را وارد کنید.",
    )
    # visitor analytics and customer chat (templates/partials/analytics_head.html, contact_float.html)
    ga_measurement_id = models.CharField(
        _("Google Analytics ID"), max_length=20, blank=True,
        validators=[RegexValidator(r"^G-[A-Z0-9]{4,16}$", "شناسه را به شکل G-XXXXXXXXXX وارد کنید.")],
        help_text="شناسه اندازه‌گیری Google Analytics 4، مثلاً G-ABC123XYZ. بازدید کالا، افزودن به سبد، "
                  "شروع پرداخت و خرید به‌صورت رویداد ثبت می‌شوند.",
    )
    analytics_head_html = models.TextField(
        _("analytics code"), blank=True,
        help_text="کد سرویس آمار دیگر را دقیقاً همان‌طور که سرویس می‌دهد اینجا بچسبانید؛ در head همه صفحات قرار می‌گیرد.",
    )
    whatsapp_number = models.CharField(
        _("WhatsApp number"), max_length=15, blank=True,
        validators=[RegexValidator(r"^98\d{10}$", "شماره را با کد کشور، بدون صفر و +، وارد کنید؛ مثلاً 989121234567.")],
        help_text="دکمه شناور واتس‌اپ؛ به شکل 989121234567",
    )
    telegram_username = models.CharField(
        _("Telegram username"), max_length=40, blank=True,
        validators=[RegexValidator(r"^[A-Za-z0-9_]{5,32}$", "نام کاربری تلگرام را بدون @ وارد کنید.")],
        help_text="دکمه شناور تلگرام؛ نام کاربری بدون @",
    )
    chat_widget_html = models.TextField(
        _("live chat code"), blank=True,
        help_text="کد ابزار گفتگوی آنلاین (مثلاً گفتینو یا رایچت) را دقیقاً همان‌طور که سرویس می‌دهد اینجا بچسبانید؛ "
                  "در انتهای همه صفحات قرار می‌گیرد.",
    )

    # customer club (apps.loyalty): points for delivered orders, turned into wallet credit; referral rewards
    loyalty_enabled = models.BooleanField(
        _("customer club enabled"), default=True,
        help_text="امتیاز خرید و معرفی دوستان. با خاموش کردن، امتیاز جدیدی داده نمی‌شود و صفحه باشگاه پنهان می‌شود.",
    )
    loyalty_toman_per_point = models.PositiveIntegerField(
        _("Toman per point"), default=10_000,
        validators=[MinValueValidator(1)],
        help_text="به ازای هر چند تومان خرید (مبلغ کالاها پس از تخفیف، بدون هزینه ارسال و نصب) یک امتیاز داده شود. "
                  "امتیاز پس از تحویل سفارش ثبت می‌شود.",
    )
    loyalty_point_value = models.PositiveIntegerField(
        _("point value"), default=100,
        help_text="ارزش هر امتیاز به تومان هنگام تبدیل به اعتبار کیف پول. با مقادیر پیش‌فرض، مشتری ۱٪ خریدش را پس می‌گیرد.",
    )
    loyalty_min_redeem_points = models.PositiveIntegerField(
        _("minimum points to redeem"), default=500,
        help_text="کمترین امتیازی که یک‌جا به اعتبار تبدیل می‌شود.",
    )
    referral_referrer_points = models.PositiveIntegerField(
        _("referrer reward points"), default=2_000,
        help_text="امتیاز معرف، وقتی اولین خرید دوستش تحویل شود.",
    )
    referral_friend_points = models.PositiveIntegerField(
        _("new customer reward points"), default=1_000,
        help_text="امتیاز هدیه مشتری تازه‌واردی که با کد معرف آمده، پس از تحویل اولین خریدش.",
    )
    referral_min_order_amount = models.BigIntegerField(
        _("referral minimum order"), default=1_000_000,
        help_text="پاداش معرفی فقط وقتی داده می‌شود که مبلغ کالاهای آن خرید دست‌کم این مقدار (تومان) باشد.",
    )

    # stock forecast (apps.catalog.forecast)
    restock_lead_days = models.PositiveIntegerField(
        _("supplier lead time (days)"), default=7,
        help_text="از سفارش به تأمین‌کننده تا رسیدن کالا به انبار معمولاً چند روز طول می‌کشد؛ "
                  "کالایی که زودتر از این تمام شود «فوری» علامت می‌خورد.",
    )
    # win-back campaign (apps.crm): a personal coupon for customers who stopped buying
    winback_enabled = models.BooleanField(
        _("win-back campaign enabled"), default=False,
        help_text="با روشن کردن، به مشتریانی که مدتی خرید نکرده‌اند خودکار یک کد تخفیف شخصی پیامک یا ایمیل می‌شود. "
                  "مشتریانی که در پروفایل، دریافت پیشنهادها را خاموش کرده‌اند پیامی نمی‌گیرند.",
    )
    winback_after_days = models.PositiveIntegerField(
        _("inactive after (days)"), default=120, validators=[MinValueValidator(30)],
        help_text="مشتری‌ای که این مدت از آخرین خریدش گذشته «خوابیده» حساب می‌شود و پیشنهاد می‌گیرد.",
    )
    winback_percent = models.PositiveIntegerField(
        _("win-back discount (%)"), default=10, validators=[MinValueValidator(1), MaxValueValidator(100)],
    )
    winback_max_discount = models.BigIntegerField(
        _("win-back discount cap"), null=True, blank=True, default=1_000_000,
        help_text="سقف تخفیف به تومان؛ خالی = بدون سقف",
    )
    winback_valid_days = models.PositiveIntegerField(
        _("win-back code valid for (days)"), default=14, validators=[MinValueValidator(1)],
    )

    class Meta:
        verbose_name = _("site settings")
        verbose_name_plural = _("site settings")

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete("site_settings")

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ContactMessage(models.Model):
    name = models.CharField(_("name"), max_length=120)
    email = models.EmailField(_("email"))
    subject = models.CharField(_("subject"), max_length=200)
    body = models.TextField(_("message"), max_length=5000)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    is_read = models.BooleanField(_("read"), default=False)

    class Meta:
        verbose_name = _("contact message")
        verbose_name_plural = _("contact messages")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name}: {self.subject}"


class StaticPage(models.Model):
    class PageKey(models.TextChoices):
        FAQ = "faq", _("FAQ")
        RETURN_POLICY = "return_policy", _("return policy")
        TERMS = "terms", _("terms and conditions")
        PRIVACY = "privacy", _("privacy policy")

    key = models.CharField(_("key"), max_length=20, choices=PageKey.choices, unique=True)
    title = models.CharField(_("title"), max_length=200)
    body = models.TextField(_("body"), help_text=_("Markdown-like plain text; blank line = new paragraph"))
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("static page")
        verbose_name_plural = _("static pages")

    def __str__(self):
        return self.title

    def paragraphs(self):
        return [p.strip() for p in self.body.split("\n\n") if p.strip()]
