from pathlib import Path
import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_DB=(str, "sqlite"),
    DJANGO_SECRET_KEY=(str, "insecure-dev-key-change-me"),
    SENTRY_DSN=(str, ""),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# Sentry error tracking (production only — set SENTRY_DSN in .env)
if env("SENTRY_DSN"):
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=env("SENTRY_DSN"),
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.0,
        send_default_pii=False,
        environment="production" if not DEBUG else "development",
    )

# ---------------------------------------------------------------- apps
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "django.contrib.humanize",
    "rest_framework",
    "apps.common",
    "apps.accounts",
    "apps.catalog",
    "apps.cart",
    "apps.discounts",
    "apps.orders",
    "apps.payments",
    "apps.reviews",
    "apps.wallet",
    "apps.newsletter",
    "apps.blog",
    "apps.wishlist",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.common.context_processors.site_settings",
                "apps.wishlist.context_processors.wishlist",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------- db
if env("DJANGO_DB") == "postgres":
    DATABASES = {"default": env.db("DATABASE_URL")}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ---------------------------------------------------------------- auth
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------- i18n
LANGUAGE_CODE = "fa"
# Persian labels for English gettext strings (locale/fa/LC_MESSAGES/django.po -> manage.py compile_po)
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------- static / media
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------- misc
SITE_STORE_NAME = "فروشگاه من"
SITE_URL = env("SITE_URL", default="http://127.0.0.1:8000")

# ---------------------------------------------------------------- payments
PAYMENT_GATEWAY = env("PAYMENT_GATEWAY", default="apps.payments.gateways.MockGateway")
ZARINPAL = {
    "MERCHANT_ID": env("ZARINPAL_MERCHANT_ID", default=""),
    "SANDBOX": env.bool("ZARINPAL_SANDBOX", default=True),
}

# ---------------------------------------------------------------- orders
# unpaid orders are cancelled (stock + coupon released) by `manage.py expire_unpaid_orders`
ORDER_PAYMENT_TIMEOUT_MINUTES = env.int("ORDER_PAYMENT_TIMEOUT_MINUTES", default=30)
# ...unless a gateway payment started this recently (customer may still be at the bank)
ORDER_PAYMENT_GRACE_MINUTES = env.int("ORDER_PAYMENT_GRACE_MINUTES", default=15)
# days after delivery a customer can open a return request (7 = statutory withdrawal period for online purchases)
RETURN_WINDOW_DAYS = env.int("RETURN_WINDOW_DAYS", default=7)
# managers alerted when an order is paid: SMS numbers, and emails (empty = ADMINS)
ORDER_NOTIFY_PHONES = env.list("ORDER_NOTIFY_PHONES", default=[])
ORDER_NOTIFY_EMAILS = env.list("ORDER_NOTIFY_EMAILS", default=[])

# ---------------------------------------------------------------- rate limiting
RATELIMIT_ENABLE = env.bool("RATELIMIT_ENABLE", default=True)
# request.META key holding the real client IP when behind a proxy that sets it, e.g. HTTP_X_REAL_IP
RATELIMIT_IP_HEADER = env("RATELIMIT_IP_HEADER", default="")

# ---------------------------------------------------------------- SMS / phone login
SMS_BACKEND = env("SMS_BACKEND", default="apps.common.sms.FileSmsBackend")
SMS_FILE_PATH = BASE_DIR / "sent_sms"  # FileSmsBackend output (development)
SMSIR = {
    "API_KEY": env("SMSIR_API_KEY", default=""),
    "LINE_NUMBER": env("SMSIR_LINE_NUMBER", default=""),
    "OTP_TEMPLATE_ID": env.int("SMSIR_OTP_TEMPLATE_ID", default=0),
    "OTP_PARAMETER": env("SMSIR_OTP_PARAMETER", default="CODE"),
}
OTP_LENGTH = 5
OTP_TTL_SECONDS = env.int("OTP_TTL_SECONDS", default=120)
OTP_RESEND_SECONDS = env.int("OTP_RESEND_SECONDS", default=60)
OTP_MAX_ATTEMPTS = 5

# ---------------------------------------------------------------- drf
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}

# ---------------------------------------------------------------- logging
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "error_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "error.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
            "level": "ERROR",
            "encoding": "utf-8",
        },
        "shop_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "shop.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
            "level": "INFO",
            "encoding": "utf-8",
        },
        "mail_admins": {
            "class": "django.utils.log.AdminEmailHandler",
            "level": "ERROR",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["error_file"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["error_file"],
            "level": "ERROR",
            "propagate": False,
        },
        "shop2": {
            "handlers": ["error_file"],
            "level": "INFO",
            "propagate": False,
        },
        "shop": {
            "handlers": ["shop_file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

ADMINS = [("Admin", env("ADMIN_EMAIL", default="admin@shop.local"))]
