from apps.catalog.models import Product
from apps.reviews.models import Review


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
