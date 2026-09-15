"""Scaled-down WebP copies of uploaded photos, made on first use and kept in MEDIA_ROOT/thumbs/.

A 4 MB phone photo shown in a 300px product card becomes a file of a few dozen KB; nginx
serves the copies like any other media file.
"""
import hashlib
import logging
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

logger = logging.getLogger("shop")
QUALITY = 80


def thumbnail_name(image_name: str, width: int) -> str:
    digest = hashlib.sha1(image_name.encode()).hexdigest()[:20]
    return f"thumbs/{width}/{digest}.webp"


def thumbnail_url(image, width: int) -> str:
    """URL of the image at most `width` px wide as WebP; the original URL if a copy can't be made."""
    if not image:
        return ""
    name = thumbnail_name(image.name, width)
    if default_storage.exists(name):
        return default_storage.url(name)
    try:
        from PIL import Image, ImageOps

        with image.storage.open(image.name, "rb") as fh, Image.open(fh) as source:
            picture = ImageOps.exif_transpose(source)  # phone photos store rotation separately
            if picture.mode not in ("RGB", "RGBA"):
                picture = picture.convert("RGBA" if picture.mode in ("P", "LA", "PA") else "RGB")
            if picture.width > width:  # never enlarge
                picture.thumbnail((width, width * 10), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            picture.save(buffer, "WEBP", quality=QUALITY, method=4)
        default_storage.save(name, ContentFile(buffer.getvalue()))
    except Exception as exc:  # missing file, unreadable image, disk error: the page still shows the original
        logger.warning("THUMBNAIL_FAIL image=%s width=%s error=%s", image.name, width, exc)
        return image.url
    return default_storage.url(name)
