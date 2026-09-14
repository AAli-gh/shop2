from django.contrib.sitemaps import Sitemap

from apps.blog.models import Post
from apps.catalog.models import Category, Product


class PostSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6

    def items(self):
        return Post.objects.filter(is_published=True)

    def lastmod(self, obj):
        return obj.published_at


class ProductSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.9

    def items(self):
        return Product.objects.filter(is_active=True).order_by("-updated_at")

    def lastmod(self, obj):
        return obj.updated_at


class CategorySitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return Category.objects.filter(is_active=True)

    def lastmod(self, obj):
        products = obj.products.order_by("-updated_at").first()
        return products.updated_at if products else None


class StaticViewSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.5

    def items(self):
        return ["catalog:home", "catalog:product_list", "common:about", "common:contact"]

    def location(self, item):
        from django.urls import reverse

        return reverse(item)
