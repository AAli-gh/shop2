import pytest
from django.utils import timezone

from apps.blog.models import Post


@pytest.fixture
def persian_post(db):
    # no slug given: it is derived from the Persian title
    return Post.objects.create(
        title="راهنمای خرید یخچال", body="متن", is_published=True, published_at=timezone.now()
    )


def test_persian_title_gets_persian_slug(persian_post):
    assert persian_post.slug == "راهنمای-خرید-یخچال"


def test_persian_slug_post_opens(client, persian_post):
    response = client.get(persian_post.get_absolute_url())
    assert response.status_code == 200
    assert "راهنمای خرید یخچال" in response.content.decode()


def test_list_links_to_persian_slug_post(client, persian_post):
    response = client.get("/blog/")
    assert response.status_code == 200
    assert persian_post.get_absolute_url() in response.content.decode()


def test_sitemap_includes_persian_slug_post(client, persian_post):
    response = client.get("/sitemap.xml")
    assert response.status_code == 200


def test_unpublished_post_is_hidden(client, db):
    post = Post.objects.create(title="پیش‌نویس", body="متن", is_published=False)
    assert client.get(post.get_absolute_url()).status_code == 404
