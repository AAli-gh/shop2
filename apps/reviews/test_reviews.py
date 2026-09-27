import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.catalog.models import Category, Product
from apps.reviews.models import Review


@pytest.fixture
def product(db):
    category = Category.objects.create(name="یخچال", slug="fridge")
    return Product.objects.create(category=category, name="یخچال ساید", slug="side", price=50_000_000, stock=3)


@pytest.fixture
def signed_in(client, django_user_model):
    client.force_login(django_user_model.objects.create_user(email="r@example.com", password="x"))
    return client


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buf, "PNG")
    return buf.getvalue()


def _submit(client, product, upload):
    return client.post(
        f"/reviews/product/{product.pk}/submit/",
        {"rating": 5, "body": "خیلی خوب است", "image": upload},
    )


def test_real_photo_is_accepted(signed_in, product, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    _submit(signed_in, product, SimpleUploadedFile("photo.png", _png(), content_type="image/png"))
    assert Review.objects.get().image.name.endswith(".png")


@pytest.mark.parametrize("name, content", [
    ("evil.html", b"<script>alert(1)</script>"),               # page labelled as a photo
    ("evil.png", b"<script>alert(1)</script>"),                # not an image at all
    ("evil.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"),
    ("evil.html", None),                                        # real PNG bytes, but saved as .html
])
def test_disguised_files_are_refused(signed_in, product, settings, tmp_path, name, content):
    settings.MEDIA_ROOT = tmp_path
    upload = SimpleUploadedFile(name, content or _png(), content_type="image/png")
    response = _submit(signed_in, product, upload)
    assert response.status_code == 200
    assert not Review.objects.exists()
