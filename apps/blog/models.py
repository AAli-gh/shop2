from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


class Post(models.Model):
    class Kind(models.TextChoices):
        ARTICLE = "article", "مقاله"
        GUIDE = "guide", "راهنمای خرید"

    title = models.CharField(_("title"), max_length=200)
    slug = models.SlugField(_("slug"), max_length=220, unique=True, allow_unicode=True)
    excerpt = models.CharField(_("summary"), max_length=300, blank=True)
    body = models.TextField(_("body"), help_text="خط خالی = پاراگراف جدید؛ خطی که با ## شروع شود = تیتر")
    cover = models.ImageField(_("cover image"), upload_to="blog/", blank=True)
    kind = models.CharField(_("kind"), max_length=10, choices=Kind.choices, default=Kind.ARTICLE)
    is_published = models.BooleanField(_("published"), default=False)
    published_at = models.DateTimeField(_("published at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("blog post")
        verbose_name_plural = _("blog posts")
        ordering = ["-published_at", "-created_at"]
        indexes = [models.Index(fields=["is_published", "-published_at"])]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title, allow_unicode=True)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("blog:detail", kwargs={"slug": self.slug})

    def blocks(self):
        out = []
        for chunk in (self.body or "").split("\n\n"):
            chunk = chunk.strip()
            if not chunk:
                continue
            if chunk.startswith("## "):
                out.append({"h2": chunk[3:].strip()})
            else:
                out.append({"p": chunk})
        return out
