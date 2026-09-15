import io

import pytest
from django.core.files.base import ContentFile
from PIL import Image

from apps.catalog.models import Category, Product
from apps.common import thumbnails
from apps.common.thumbnails import thumbnail_name, thumbnail_url


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def _product_with_photo(size=(1600, 1200), data=None):
    if data is None:
        buffer = io.BytesIO()
        Image.new("RGB", size, "orange").save(buffer, "JPEG", quality=95)
        data = buffer.getvalue()
    category = Category.objects.create(name="c", slug="c")
    product = Product.objects.create(category=category, name="p", slug="p", price=10, stock=1)
    product.image.save("photo.jpg", ContentFile(data))
    return product


@pytest.mark.django_db
def test_a_large_photo_becomes_a_small_webp(media):
    product = _product_with_photo()

    url = thumbnail_url(product.image, 400)

    path = media / thumbnail_name(product.image.name, 400)
    assert url == f"/media/{thumbnail_name(product.image.name, 400)}"
    with Image.open(path) as copy:
        assert (copy.format, copy.size) == ("WEBP", (400, 300))
    assert path.stat().st_size < (media / product.image.name).stat().st_size


@pytest.mark.django_db
def test_small_photos_are_not_enlarged(media):
    product = _product_with_photo(size=(200, 100))
    thumbnail_url(product.image, 400)
    with Image.open(media / thumbnail_name(product.image.name, 400)) as copy:
        assert copy.size == (200, 100)


@pytest.mark.django_db
def test_the_copy_is_made_once(monkeypatch):
    product = _product_with_photo()
    first = thumbnail_url(product.image, 400)

    def fail(*args, **kwargs):
        raise AssertionError("the image should not be processed again")

    monkeypatch.setattr(thumbnails.default_storage, "save", fail)
    assert thumbnail_url(product.image, 400) == first


@pytest.mark.django_db
def test_an_unreadable_file_falls_back_to_the_original():
    product = _product_with_photo(data=b"not an image")
    assert thumbnail_url(product.image, 400) == product.image.url


@pytest.mark.django_db
def test_listings_use_the_thumbnail(client):
    _product_with_photo()
    assert "/media/thumbs/400/" in client.get("/products/").content.decode()
