from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class WishlistItem(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="wishlist_items",
        on_delete=models.CASCADE, verbose_name=_("user"),
    )
    product = models.ForeignKey(
        "catalog.Product", related_name="wishlist_items",
        on_delete=models.CASCADE, verbose_name=_("product"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("wishlist item")
        verbose_name_plural = _("wishlist items")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "product"], name="unique_wishlist_item"),
        ]

    def __str__(self):
        return f"{self.user} ♥ {self.product}"
