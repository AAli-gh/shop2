from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


class Cart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        related_name="cart", on_delete=models.CASCADE, verbose_name=_("user"),
    )
    session_key = models.CharField(_("session key"), max_length=40, null=True, blank=True, unique=True)
    # touched whenever items change (apps.cart.services), so it tells when the customer last used the cart
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    # last abandoned-cart SMS; another is sent only after the cart changes again
    reminded_at = models.DateTimeField(_("reminded at"), null=True, blank=True)

    class Meta:
        verbose_name = _("cart")
        verbose_name_plural = _("carts")
        constraints = [
            models.CheckConstraint(
                condition=Q(user__isnull=False, session_key__isnull=True)
                | Q(user__isnull=True, session_key__isnull=False),
                name="cart_single_owner",
            ),
        ]

    def __str__(self):
        return f"Cart #{self.pk} ({self.user or self.session_key})"


class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart, related_name="items", on_delete=models.CASCADE, verbose_name=_("cart")
    )
    product = models.ForeignKey(
        "catalog.Product", related_name="cart_items", on_delete=models.CASCADE,
        verbose_name=_("product"),
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant", null=True, blank=True, related_name="cart_items", on_delete=models.CASCADE,
        verbose_name=_("variant"),
    )
    quantity = models.PositiveSmallIntegerField(_("quantity"), default=1)

    class Meta:
        verbose_name = _("cart item")
        verbose_name_plural = _("cart items")
        constraints = [
            models.UniqueConstraint(fields=["cart", "product"], condition=Q(variant__isnull=True),
                                    name="unique_product_per_cart"),
            models.UniqueConstraint(fields=["cart", "variant"], condition=Q(variant__isnull=False),
                                    name="unique_variant_per_cart"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="cart_item_quantity_positive"),
        ]

    def __str__(self):
        return f"{self.product} x{self.quantity}"

    @property
    def offer(self):
        """What is being bought — the chosen variant, or the product itself — for its price and stock."""
        return self.variant or self.product
