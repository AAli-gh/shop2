from .base import *  # noqa: F401,F403

DEBUG = True

# File-based email backend for development (emails land in sent_emails/)
EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
EMAIL_FILE_PATH = BASE_DIR / "sent_emails"

DEFAULT_FROM_EMAIL = "no-reply@shop.local"
