from django.utils import timezone

from apps.catalog.models import Product
from apps.reviews.models import ProductQuestion, Review

MIN_QUESTION_LENGTH = 10
MAX_QUESTION_LENGTH = 1000


def submit_review(*, user, product_id: int, rating: int, body: str, image=None) -> Review:
    product = Product.objects.get(pk=product_id)
    review = Review.objects.filter(product=product, user=user).first()
    if review:
        review.rating = rating
        review.body = body
        review.is_approved = False
        if image:
            review.image = image
        review.save()
    else:
        review = Review.objects.create(
            product=product, user=user, rating=rating, body=body, image=image, is_approved=False,
        )
    return review


def approved_reviews_for(product):
    return product.reviews.filter(is_approved=True).select_related("user")


def has_reviewed(*, user, product) -> bool:
    return product.reviews.filter(user=user).exists()


# ---------------------------------------------------------------- questions & answers

def ask_question(*, user, product, body: str) -> ProductQuestion:
    return ProductQuestion.objects.create(product=product, user=user, body=body)


def published_questions_for(product):
    return product.questions.filter(is_published=True).exclude(answer="").select_related("user")


def mark_first_answer(question: ProductQuestion, *, staff_user) -> None:
    """Stamp a question receiving its first answer and publish it (staff can unpublish on a later save)."""
    question.answered_by = staff_user
    question.answered_at = timezone.now()
    question.is_published = True


def notify_answer(question: ProductQuestion) -> None:
    """Tell the customer their question was answered: SMS to a verified mobile, otherwise email."""
    from django.conf import settings
    from django.core.mail import send_mail

    from apps.common import sms
    from apps.common.services import get_settings

    user, product = question.user, question.product
    url = f"{settings.SITE_URL.rstrip('/')}{product.get_absolute_url()}#questions-section"
    if user.phone and user.phone_verified:
        sms.notify(user.phone, f"{get_settings().store_name}: به پرسش شما درباره «{product.name}» پاسخ داده شد. {url}")
    elif user.email:
        send_mail(
            f"پاسخ پرسش شما درباره {product.name}",
            f"پرسش شما:\n{question.body}\n\nپاسخ:\n{question.answer}\n\n{url}",
            settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True,
        )
