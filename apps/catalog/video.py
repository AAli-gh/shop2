"""Turn a product's video link into a player that plays inside the page.

Only Aparat and YouTube are recognised; anything else keeps its plain link, so a wrong
address can never put an arbitrary iframe on the product page.
"""
import re

APARAT = re.compile(r"aparat\.com/(?:v/|video/video/embed/videohash/)([A-Za-z0-9]+)")
YOUTUBE = re.compile(r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([A-Za-z0-9_-]{6,})")


def embed_url(url: str) -> str:
    """Embeddable player URL, or "" when the link isn't one we can play."""
    match = APARAT.search(url or "")
    if match:
        return f"https://www.aparat.com/video/video/embed/videohash/{match.group(1)}/vt/frame"
    match = YOUTUBE.search(url or "")
    if match:
        return f"https://www.youtube.com/embed/{match.group(1)}"
    return ""
