"""Fixed-window rate limiting on Django's cache (no extra dependency).

Counters live in the default cache, so production needs a cache shared by every
worker process (file or Redis cache — see config/settings/prod.py); with the
per-process LocMem cache each worker would count on its own.
"""
import functools
import hashlib
import time

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import render


def client_ip(request) -> str:
    """Client address; behind a reverse proxy set RATELIMIT_IP_HEADER (e.g. HTTP_X_REAL_IP)."""
    header = getattr(settings, "RATELIMIT_IP_HEADER", "")
    if header:
        value = request.META.get(header, "")
        if value:
            return value.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or "unknown"


def is_limited(scope: str, ident: str, *, limit: int, window: int) -> bool:
    """Count one attempt for (scope, ident); True once this window's count exceeds limit."""
    if not getattr(settings, "RATELIMIT_ENABLE", True):
        return False
    bucket = int(time.time() // window)
    digest = hashlib.sha256(f"{scope}:{ident}".encode()).hexdigest()[:32]
    key = f"rl:{scope}:{digest}:{bucket}"
    if cache.add(key, 1, timeout=window):
        return 1 > limit
    try:
        count = cache.incr(key)
    except ValueError:  # expired between add() and incr()
        cache.set(key, 1, timeout=window)
        count = 1
    return count > limit


def limited_response(request, retry_after: int):
    if request.headers.get("HX-Request"):
        response = HttpResponse(
            "تعداد درخواست‌ها بیش از حد مجاز است. چند دقیقه بعد دوباره تلاش کنید.",
            status=429, content_type="text/plain; charset=utf-8",
        )
    else:
        response = render(request, "429.html", {"retry_minutes": max(1, retry_after // 60)}, status=429)
    response["Retry-After"] = str(retry_after)
    return response


def ratelimit(scope: str, *, limit: int, window: int, methods=("POST",), key_fields=(), key_limit=None):
    """View decorator: at most `limit` requests per `window` seconds per client IP.

    Each POST field in `key_fields` (e.g. the login email) gets its own counter too,
    capped at `key_limit` (default `limit`), so guessing against one account is
    stopped even when spread over many IPs.
    """
    def decorator(view):
        @functools.wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method in methods:
                ip = client_ip(request)
                counters = [(f"ip:{ip}", limit)]
                for field in key_fields:
                    value = (request.POST.get(field) or "").strip().lower()
                    if value:
                        counters.append((f"{field}:{value}", key_limit or limit))
                # count every identity, even when an earlier one is already over its limit
                hits = [is_limited(scope, ident, limit=cap, window=window) for ident, cap in counters]
                if any(hits):
                    from apps.common import shoplog

                    shoplog.rate_limited(scope, ip)
                    return limited_response(request, window)
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
