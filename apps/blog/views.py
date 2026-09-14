from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render

from apps.blog.models import Post


def post_list(request):
    posts = Post.objects.filter(is_published=True)
    kind = request.GET.get("kind")
    if kind in dict(Post.Kind.choices):
        posts = posts.filter(kind=kind)
    paginator = Paginator(posts, 9)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(
        request, "blog/post_list.html", {"page_obj": page_obj, "current_kind": kind or ""}
    )


def post_detail(request, slug):
    post = get_object_or_404(Post, slug=slug, is_published=True)
    related = Post.objects.filter(is_published=True).exclude(pk=post.pk)[:3]
    return render(request, "blog/post_detail.html", {"post": post, "related": related})
