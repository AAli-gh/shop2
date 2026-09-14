from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


class Review(models.Model):
    product = models.ForeignKey(
        "catalog.Product", related_name="reviews", on_delete=models.CASCADE,
        verbose_name=_("product"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="reviews", on_delete=models.CASCADE,
        verbose_name=_("user"),
    )
    rating = models.PositiveSmallIntegerField(_("rating"))
    body = models.TextField(_("review body"), max_length=2000)
    image = models.ImageField(_("photo"), upload_to="reviews/", blank=True)
    is_approved = models.BooleanField(_("approved"), default=False, db_index=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("review")
        verbose_name_plural = _("reviews")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["product", "user"], name="unique_review_per_user_product"),
            models.CheckConstraint(condition=Q(rating__gte=1, rating__lte=5), name="review_rating_1_to_5"),
        ]

    def __str__(self):
        return f"{self.user} on {self.product}: {self.rating}"
