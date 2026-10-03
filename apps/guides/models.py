from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class BuyingGuide(models.Model):
    """A short questionnaire that picks products of one category for the customer (apps.guides.services)."""

    category = models.OneToOneField(
        "catalog.Category", related_name="buying_guide", on_delete=models.CASCADE, verbose_name=_("category"),
    )
    title = models.CharField(_("title"), max_length=150, help_text="مثلاً: کدام یخچال برای شما مناسب است؟")
    intro = models.CharField(_("introduction"), max_length=300, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    sort_order = models.PositiveSmallIntegerField(_("sort order"), default=0)

    class Meta:
        verbose_name = _("buying guide")
        verbose_name_plural = _("buying guides")
        ordering = ["sort_order", "title"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("guides:detail", kwargs={"category_slug": self.category.slug})

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete("has_buying_guides")  # the header link appears (or goes) right away


class GuideQuestion(models.Model):
    guide = models.ForeignKey(BuyingGuide, related_name="questions", on_delete=models.CASCADE, verbose_name=_("buying guide"))
    text = models.CharField(_("question"), max_length=200, help_text="مثلاً: چند نفر در خانه زندگی می‌کنید؟")
    hint = models.CharField(_("hint"), max_length=200, blank=True)
    sort_order = models.PositiveSmallIntegerField(_("sort order"), default=0)

    class Meta:
        verbose_name = _("guide question")
        verbose_name_plural = _("guide questions")
        ordering = ["sort_order", "pk"]

    def __str__(self):
        return self.text


class GuideAnswer(models.Model):
    """One option of a question and the rule it adds: a range or word on a spec, and/or a price range.

    An option with no rule («فرقی نمی‌کند») changes nothing. A required rule removes products that
    don't meet it; any other rule only moves matching products up the list.
    """

    question = models.ForeignKey(GuideQuestion, related_name="answers", on_delete=models.CASCADE, verbose_name=_("question"))
    label = models.CharField(_("option"), max_length=120, help_text="مثلاً: ۳ تا ۴ نفر")
    sort_order = models.PositiveSmallIntegerField(_("sort order"), default=0)
    attribute = models.ForeignKey(
        "catalog.Attribute", null=True, blank=True, on_delete=models.CASCADE, verbose_name=_("spec"),
        help_text="مشخصه فنی همین دسته که این گزینه با آن سنجیده می‌شود؛ مثلاً ظرفیت",
    )
    min_value = models.DecimalField(
        _("from"), max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="کمترین مقدار عددی مشخصه (مثلاً ۴۰۰ برای ظرفیت ۴۰۰ لیتر به بالا)",
    )
    max_value = models.DecimalField(_("to"), max_digits=12, decimal_places=2, null=True, blank=True,
                                    help_text="بیشترین مقدار عددی مشخصه")
    text_contains = models.CharField(
        _("contains"), max_length=100, blank=True,
        help_text="برای مشخصه متنی: کلمه‌ای که باید در مقدار آن باشد؛ مثلاً اینورتر",
    )
    price_min = models.BigIntegerField(_("price from"), null=True, blank=True, help_text=_("in Toman"))
    price_max = models.BigIntegerField(_("price to"), null=True, blank=True, help_text=_("in Toman"))
    is_required = models.BooleanField(
        _("required"), default=False,
        help_text="کالایی که این شرط را ندارد اصلاً پیشنهاد نشود (مثلاً سقف بودجه یا عرض جای یخچال).",
    )
    reason = models.CharField(
        _("reason shown"), max_length=150, blank=True,
        help_text="کنار کالای مناسب نمایش داده می‌شود؛ مثلاً «مناسب خانواده ۳ تا ۴ نفره». خالی = مقدار مشخصه.",
    )

    class Meta:
        verbose_name = _("guide option")
        verbose_name_plural = _("guide options")
        ordering = ["sort_order", "pk"]

    def __str__(self):
        return self.label

    @property
    def has_rule(self) -> bool:
        return bool(
            self.attribute_id and (self.min_value is not None or self.max_value is not None or self.text_contains)
        ) or self.price_min is not None or self.price_max is not None

    def clean(self):
        if self.attribute_id and not (self.min_value is not None or self.max_value is not None or self.text_contains):
            raise ValidationError("برای مشخصه انتخاب‌شده، بازهٔ عددی یا کلمهٔ موردنظر را وارد کنید.")
        if (self.min_value is not None or self.max_value is not None or self.text_contains) and not self.attribute_id:
            raise ValidationError({"attribute": "بازه یا کلمه بدون انتخاب مشخصه معنی ندارد."})
        if self.attribute_id and self.question_id:
            category = self.question.guide.category
            # the guide's category, its parent, or one of its subcategories
            related = {category.pk, category.parent_id, *category.children.values_list("pk", flat=True)}
            if self.attribute.category_id not in related:
                raise ValidationError({"attribute": f"این مشخصه متعلق به دستهٔ «{category}» نیست."})
        for low, high in ((self.min_value, self.max_value), (self.price_min, self.price_max)):
            if low is not None and high is not None and low > high:
                raise ValidationError("مقدار «از» نباید بیشتر از «تا» باشد.")
