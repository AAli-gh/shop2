"""Bug 3: production settings. They read the environment at import time, so each case
runs in a fresh interpreter with a controlled environment."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parents[2]

PROD_ENV = {
    "DJANGO_SETTINGS_MODULE": "config.settings.prod",
    "DJANGO_SECRET_KEY": "prod-test-secret-9f3kQ2vL8xR1mZ7tB4nW6yH0cJ5sD2gPa7Kx",
    "DJANGO_ALLOWED_HOSTS": "shop.example.com",
    "DJANGO_DEBUG": "False",
    "EMAIL_HOST": "smtp.example.com",
    "PAYMENT_GATEWAY": "apps.payments.gateways.ZarinPalGateway",
    "ZARINPAL_MERCHANT_ID": "00000000-0000-0000-0000-000000000000",
}
OWNED_PREFIXES = ("DJANGO_", "EMAIL_", "PAYMENT_", "ZARINPAL_", "ALLOW_MOCK", "SITE_URL", "CACHE_URL", "RATELIMIT_")


def run_python(args, **overrides):
    env = {k: v for k, v in os.environ.items() if not k.startswith(OWNED_PREFIXES)}
    env.update(PROD_ENV)
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, *args], cwd=BASE_DIR, env=env,
        capture_output=True, text=True, encoding="utf-8", timeout=120,
    )


def test_deploy_check_passes():
    result = run_python(["manage.py", "check", "--deploy", "--fail-level", "WARNING"])
    assert result.returncode == 0, result.stdout + result.stderr


def test_security_values():
    code = (
        "import django, json; django.setup(); from django.conf import settings as s; "
        "print(json.dumps({'debug': s.DEBUG, 'ssl': s.SECURE_SSL_REDIRECT, 'hsts': s.SECURE_HSTS_SECONDS, "
        "'cookies': s.SESSION_COOKIE_SECURE and s.CSRF_COOKIE_SECURE, 'csrf': s.CSRF_TRUSTED_ORIGINS, "
        "'site': s.SITE_URL, 'email': s.EMAIL_BACKEND, 'cache': s.CACHES['default']['BACKEND'], "
        "'ip_header': s.RATELIMIT_IP_HEADER}))"
    )
    result = run_python(["-c", code])
    assert result.returncode == 0, result.stderr
    values = json.loads(result.stdout.strip().splitlines()[-1])
    assert values["debug"] is False
    assert values["ssl"] is True and values["hsts"] > 0 and values["cookies"] is True
    assert values["csrf"] == ["https://shop.example.com"]
    assert values["site"] == "https://shop.example.com"
    assert values["email"] == "django.core.mail.backends.smtp.EmailBackend"
    assert "locmem" not in values["cache"]  # rate limits must be shared across workers
    assert values["ip_header"] == "HTTP_X_REAL_IP"


@pytest.mark.parametrize(
    "overrides, expected_in_error",
    [
        ({"DJANGO_SECRET_KEY": "short"}, "DJANGO_SECRET_KEY"),
        ({"DJANGO_ALLOWED_HOSTS": None}, "DJANGO_ALLOWED_HOSTS"),
        ({"EMAIL_HOST": None}, "EMAIL_HOST"),
        ({"PAYMENT_GATEWAY": "apps.payments.gateways.MockGateway"}, "MockGateway"),
    ],
)
def test_unsafe_configuration_refuses_to_start(overrides, expected_in_error):
    result = run_python(["-c", "import django; django.setup()"], **overrides)
    assert result.returncode != 0
    assert expected_in_error in result.stderr


def test_mock_gateway_allowed_explicitly_for_staging():
    result = run_python(
        ["-c", "import django; django.setup()"],
        PAYMENT_GATEWAY="apps.payments.gateways.MockGateway", ALLOW_MOCK_GATEWAY="True",
    )
    assert result.returncode == 0, result.stderr


def test_wsgi_defaults_to_production_settings():
    # regression: wsgi/asgi pointed at the empty config.settings package
    code = "import os, config.wsgi; print(os.environ['DJANGO_SETTINGS_MODULE'])"
    result = run_python(["-c", code], DJANGO_SETTINGS_MODULE=None)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "config.settings.prod"
