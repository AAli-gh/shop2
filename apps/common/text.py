"""Persian text folding for search.

Shoppers type with different keyboards: Arabic «ي/ك» instead of Persian «ی/ک», Persian or
Latin digits, a half-space (ZWNJ) or a normal space. Stored text and queries are folded
the same way so all of these spellings match.
"""
import re

_CHAR_MAP = str.maketrans({
    "ي": "ی", "ى": "ی", "ئ": "ی",
    "ك": "ک",
    "ة": "ه", "ۀ": "ه",
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ؤ": "و",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4", "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4", "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    "‌": " ",  # ZWNJ (half-space)
    "‍": "",   # ZWJ
    "ـ": "",        # tatweel
})
_DIACRITICS = re.compile("[ً-ٰٟ]")
_SPACES = re.compile(r"\s+")


def normalize_search(text) -> str:
    """Fold spelling variants, digits, half-spaces and case; collapse whitespace."""
    if not text:
        return ""
    folded = _DIACRITICS.sub("", str(text).translate(_CHAR_MAP)).lower()
    return _SPACES.sub(" ", folded).strip()
