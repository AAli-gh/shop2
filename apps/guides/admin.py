from django.contrib import admin
from django.db.models import Q

from apps.guides.models import BuyingGuide, GuideAnswer, GuideQuestion


class GuideQuestionInline(admin.TabularInline):
    model = GuideQuestion
    fields = ("text", "hint", "sort_order")
    extra = 1
    show_change_link = True  # the options of a question are edited on its own page


@admin.register(BuyingGuide)
class BuyingGuideAdmin(admin.ModelAdmin):
    """A guide per category. Save the questions here, then open each one to give it options and rules."""

    list_display = ("title", "category", "question_count", "is_active", "sort_order")
    list_editable = ("is_active", "sort_order")
    list_select_related = ("category",)
    inlines = [GuideQuestionInline]

    @admin.display(description="تعداد سؤال")
    def question_count(self, obj):
        return obj.questions.count()


class GuideAnswerInline(admin.TabularInline):
    model = GuideAnswer
    fields = ("label", "attribute", "min_value", "max_value", "text_contains", "price_min", "price_max",
              "is_required", "reason", "sort_order")
    extra = 2

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # only the specs of the guide's category (its parent or subcategories too) make sense here
        question = getattr(request, "_guide_question", None)
        if db_field.name == "attribute" and question is not None:
            category = question.guide.category
            kwargs["queryset"] = db_field.related_model.objects.filter(
                Q(category=category) | Q(category__parent=category) | Q(category_id=category.parent_id)
            ).select_related("category")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(GuideQuestion)
class GuideQuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "guide", "sort_order")
    list_filter = ("guide",)
    list_select_related = ("guide",)
    inlines = [GuideAnswerInline]

    def get_form(self, request, obj=None, **kwargs):
        request._guide_question = obj
        return super().get_form(request, obj, **kwargs)

    def get_model_perms(self, request):
        return {}  # reached from a guide's question list, not from the admin menu
