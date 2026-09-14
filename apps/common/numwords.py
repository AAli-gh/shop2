"""Whole numbers in Persian words, e.g. for «مبلغ به حروف» on invoices."""

_ONES = ["", "یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "نه"]
_TEENS = ["ده", "یازده", "دوازده", "سیزده", "چهارده", "پانزده", "شانزده", "هفده", "هجده", "نوزده"]
_TENS = ["", "", "بیست", "سی", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود"]
_HUNDREDS = ["", "صد", "دویست", "سیصد", "چهارصد", "پانصد", "ششصد", "هفتصد", "هشتصد", "نهصد"]
_SCALES = ["", "هزار", "میلیون", "میلیارد", "تریلیون", "کوادریلیون"]


def _below_thousand(n: int) -> str:
    parts = []
    hundreds, rest = divmod(n, 100)
    if hundreds:
        parts.append(_HUNDREDS[hundreds])
    if 10 <= rest < 20:
        parts.append(_TEENS[rest - 10])
    else:
        tens, ones = divmod(rest, 10)
        if tens:
            parts.append(_TENS[tens])
        if ones:
            parts.append(_ONES[ones])
    return " و ".join(parts)


def number_to_words(n: int) -> str:
    if n == 0:
        return "صفر"
    if n < 0:
        return "منفی " + number_to_words(-n)
    groups = []
    scale = 0
    while n:
        if scale >= len(_SCALES):
            raise ValueError("number too large")
        n, chunk = divmod(n, 1000)
        if chunk:
            words = _below_thousand(chunk)
            groups.append(f"{words} {_SCALES[scale]}".strip())
        scale += 1
    return " و ".join(reversed(groups))
