#!/bin/bash
# Runs at the end of the build, while the filesystem is still writable but before the app's
# environment variables exist (Liara hook). Production settings refuse to start without real
# secrets, so static files are collected with throwaway values: nothing here touches the
# database or sends anything, it only writes staticfiles/ (hashed names + manifest).
set -e

echo "shop2: collecting static files"
DJANGO_SECRET_KEY="build-only-$(python -c 'import secrets; print(secrets.token_urlsafe(50))')" \
DJANGO_ALLOWED_HOSTS="build.invalid" \
EMAIL_HOST="build.invalid" \
ALLOW_MOCK_GATEWAY="True" \
ALLOW_FAKE_SMS="True" \
DJANGO_LOG_TO_STDOUT="True" \
DJANGO_CACHE_DIR="/tmp/shop2-build-cache" \
python manage.py collectstatic --noinput

echo "shop2: post-build finished"
