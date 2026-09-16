"""Production settings.

Select with DJANGO_SETTINGS_MODULE=config.settings.prod (the WSGI/ASGI default).
Everything security-relevant comes from the environment, and a missing or unsafe
value stops the process at startup instead of running an insecure site.
"""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import BASE_DIR, PAYMENT_GATEWAY, SECRET_KEY, SMS_BACKEND, SMSIR, env

DEBUG = False

if len(SECRET_KEY) < 50 or SECRET_KEY.startswith(("insecure", "change-me", "django-insecure")):
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be a long random value in production (50+ characters).")

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")  # required
CSRF_TRUSTED_ORIGINS = env.list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default=[f"https://{host}" for host in ALLOWED_HOSTS if not host.startswith(".")],
)
SITE_URL = env("SITE_URL", default=f"https://{ALLOWED_HOSTS[0]}")

if PAYMENT_GATEWAY.endswith(".MockGateway") and not env.bool("ALLOW_MOCK_GATEWAY", default=False):
    raise ImproperlyConfigured(
        "PAYMENT_GATEWAY is the MockGateway simulator, which lets anyone mark orders paid. "
        "Configure a real gateway, or set ALLOW_MOCK_GATEWAY=True for a staging server."
    )

if SMS_BACKEND.endswith((".FileSmsBackend", ".LocmemSmsBackend")) and not env.bool("ALLOW_FAKE_SMS", default=False):
    raise ImproperlyConfigured(
        "SMS_BACKEND does not send real messages, so nobody could sign in by phone. "
        "Use apps.common.sms.SmsIrBackend, or set ALLOW_FAKE_SMS=True for a staging server."
    )
if SMS_BACKEND.endswith(".SmsIrBackend") and not (SMSIR["API_KEY"] and SMSIR["OTP_TEMPLATE_ID"]):
    raise ImproperlyConfigured("SmsIrBackend needs SMSIR_API_KEY and SMSIR_OTP_TEMPLATE_ID.")

# ---------------------------------------------------------------- HTTPS (behind nginx)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 30)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)
SECURE_HSTS_PRELOAD = env.bool("DJANGO_SECURE_HSTS_PRELOAD", default=False)
# HSTS for all subdomains and the browser preload list are very hard to undo, so they stay
# opt-in; their deploy-check reminders are silenced until the site owner turns them on.
SILENCED_SYSTEM_CHECKS = [
    check for check, enabled in (
        ("security.W005", SECURE_HSTS_INCLUDE_SUBDOMAINS),
        ("security.W021", SECURE_HSTS_PRELOAD),
    ) if not enabled
]
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# ---------------------------------------------------------------- static / media
# collectstatic writes hashed files to STATIC_ROOT; nginx serves /static/ and /media/ directly
# Hashed file names need a manifest built by our own collectstatic run. A PaaS that collects static
# files itself (e.g. Liara) has no manifest, so it sets DJANGO_STATICFILES_STORAGE to the plain
# backend; templates already cache-bust the assets that change with ?v=.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": env(
        "DJANGO_STATICFILES_STORAGE",
        default="django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
    )},
}

# ---------------------------------------------------------------- email (SMTP)
# a staging server without SMTP can set this to django.core.mail.backends.dummy.EmailBackend
EMAIL_BACKEND = env("DJANGO_EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST")  # required: verification, password reset and order emails
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_TIMEOUT = 15
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default=f"no-reply@{ALLOWED_HOSTS[0].lstrip('.')}")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# ---------------------------------------------------------------- cache
# shared by all worker processes, which rate limiting depends on
if env("CACHE_URL", default=""):
    CACHES = {"default": env.cache_url("CACHE_URL")}
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
            "LOCATION": env("DJANGO_CACHE_DIR", default=str(BASE_DIR / "cache")),
        }
    }

# nginx passes the client address here (proxy_set_header X-Real-IP $remote_addr)
RATELIMIT_IP_HEADER = env("RATELIMIT_IP_HEADER", default="HTTP_X_REAL_IP")

# ---------------------------------------------------------------- admin
# password + SMS code; every staff account needs a verified mobile (deploy/README.md, step 6)
ADMIN_2FA_ENABLED = env.bool("ADMIN_2FA_ENABLED", default=True)
