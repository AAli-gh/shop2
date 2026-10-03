from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, render

from apps.guides import services
from apps.guides.models import BuyingGuide, GuideQuestion


def _active_guides():
    return BuyingGuide.objects.filter(is_active=True, category__is_active=True).select_related("category")


def guide_list(request):
    return render(request, "guides/guide_list.html", {
        "guides": _active_guides(),
        "seo_description": "به چند سؤال کوتاه جواب دهید تا مناسب‌ترین کالا را برایتان پیشنهاد کنیم.",
    })


def guide_detail(request, category_slug):
    """The questions; with answers in the query string (a shareable link) also the recommendations."""
    guide = get_object_or_404(
        _active_guides().prefetch_related(
            Prefetch("questions", queryset=GuideQuestion.objects.prefetch_related("answers")),
        ),
        category__slug=category_slug,
    )
    answers = services.chosen_answers(guide, request.GET)
    return render(request, "guides/guide_detail.html", {
        "guide": guide,
        "chosen": {answer.question_id: answer.pk for answer in answers},
        "answered": bool(answers),
        "result": services.recommend(guide, answers) if answers else None,
        "seo_description": guide.intro or guide.title,
        # every answer combination is its own URL; search engines should only index the questions
        "canonical_url": request.build_absolute_uri(guide.get_absolute_url()),
    })
