from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.catalog.models import Product
from apps.common.ratelimit import ratelimit
from apps.reviews import services

MAX_IMAGE_MB = 3
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


@login_required
@ratelimit("review", limit=10, window=3600)
def htmx_submit(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    try:
        rating = int(request.POST.get("rating", 0))
    except (TypeError, ValueError):
        rating = 0
    body = (request.POST.get("body") or "").strip()
    image = request.FILES.get("image")

    error = None
    if not 1 <= rating <= 5:
        error = "امتیاز بین ۱ تا ۵ باید باشد."
    elif len(body) < 5:
        error = "متن نظر خیلی کوتاه است."
    elif image:
        if image.size > MAX_IMAGE_MB * 1024 * 1024:
            error = f"حجم عکس حداکثر {MAX_IMAGE_MB} مگابایت است."
        elif image.content_type not in ALLOWED_IMAGE_TYPES:
            error = "فرمت عکس باید JPG، PNG یا WebP باشد."

    review = None
    if not error:
        review = services.submit_review(
            user=request.user, product_id=product.pk, rating=rating, body=body, image=image
        )
        from apps.common import shoplog

        shoplog.review_submitted(review)

    return render(
        request,
        "reviews/partials/reviews_section.html",
        {
            "product": product,
            "reviews": services.approved_reviews_for(product),
            "has_reviewed": services.has_reviewed(user=request.user, product=product),
            "submitted": review is not None,
            "error": error,
        },
    )


@login_required
@require_POST
@ratelimit("question", limit=10, window=3600)
def htmx_ask(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    body = (request.POST.get("body") or "").strip()

    error = None
    if len(body) < services.MIN_QUESTION_LENGTH:
        error = "پرسش خیلی کوتاه است؛ کمی بیشتر توضیح دهید."
    elif len(body) > services.MAX_QUESTION_LENGTH:
        error = f"پرسش حداکثر {services.MAX_QUESTION_LENGTH} نویسه می‌تواند باشد."
    else:
        services.ask_question(user=request.user, product=product, body=body)

    return render(
        request,
        "reviews/partials/questions_section.html",
        {"product": product, "questions": services.published_questions_for(product), "asked": not error, "error": error},
    )
