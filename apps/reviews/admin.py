from django.contrib import admin
from django.utils.text import Truncator

from apps.common.admin_jalali import jalali_column, jalali_date_filter
from apps.reviews import services
from apps.reviews.models import ProductQuestion, Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "user", "rating", "is_approved", "created_jalali")
    list_filter = ("is_approved", "rating", jalali_date_filter("created_at", "تاریخ ثبت"))

    created_jalali = jalali_column("created_at", "تاریخ ثبت")
    search_fields = ("product__name", "user__email", "body")
    list_editable = ("is_approved",)
    actions = ["approve_selected"]

    @admin.action(description="تأیید نظرات انتخاب‌شده")
    def approve_selected(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(request, f"{updated} نظر تأیید شد.")


class AnsweredFilter(admin.SimpleListFilter):
    title = "پاسخ"
    parameter_name = "answered"

    def lookups(self, request, model_admin):
        return (("no", "بی‌پاسخ"), ("yes", "پاسخ‌داده‌شده"))

    def queryset(self, request, queryset):
        if self.value() == "no":
            return queryset.filter(answer="")
        if self.value() == "yes":
            return queryset.exclude(answer="")
        return queryset


@admin.register(ProductQuestion)
class ProductQuestionAdmin(admin.ModelAdmin):
    list_display = ("short_body", "product", "user", "answered", "is_published", "created_jalali")
    list_filter = (AnsweredFilter, "is_published", jalali_date_filter("created_at", "تاریخ ثبت"))
    search_fields = ("body", "answer", "product__name", "user__email", "user__phone")
    fields = ("product", "user", "body", "answer", "is_published", "answered_by", "answered_jalali", "created_jalali")
    readonly_fields = ("product", "user", "body", "answered_by", "answered_jalali", "created_jalali")

    created_jalali = jalali_column("created_at", "تاریخ ثبت")
    answered_jalali = jalali_column("answered_at", "زمان پاسخ")

    @admin.display(description="پرسش")
    def short_body(self, obj):
        return Truncator(obj.body).chars(70)

    @admin.display(description="پاسخ داده شده", boolean=True)
    def answered(self, obj):
        return bool(obj.answer)

    def has_add_permission(self, request):
        return False  # questions come from product pages

    def save_model(self, request, obj, form, change):
        obj.answer = obj.answer.strip()
        first_answer = bool(obj.answer) and not ProductQuestion.objects.filter(pk=obj.pk).exclude(answer="").exists()
        if first_answer:
            services.mark_first_answer(obj, staff_user=request.user)
        super().save_model(request, obj, form, change)
        if first_answer:
            services.notify_answer(obj)
            self.message_user(request, "پاسخ منتشر شد و به مشتری اطلاع داده شد.")
