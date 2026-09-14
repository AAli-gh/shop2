#!/usr/bin/env bash
# Update the live site: pull code, install dependencies, back up, migrate, collect static, restart.
# Run from the server as an admin with sudo:   sudo /srv/shop2/deploy/deploy.sh [branch]
set -euo pipefail

BRANCH="${1:-main}"
APP_USER="shop2"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="/var/backups/shop2"

if [[ $EUID -ne 0 ]]; then
    echo "Run with sudo: sudo $0 ${BRANCH}" >&2
    exit 1
fi

# app commands run as the app user, with production settings
as_app() {
    runuser -u "$APP_USER" -- env DJANGO_SETTINGS_MODULE=config.settings.prod "$@"
}

cd "$APP_DIR"

echo "==> Updating code ($BRANCH)"
as_app git fetch --prune origin
as_app git checkout "$BRANCH"
as_app git pull --ff-only origin "$BRANCH"

echo "==> Installing dependencies"
as_app .venv/bin/pip install --quiet -r requirements-prod.txt

echo "==> Checking production configuration"
as_app .venv/bin/python manage.py check --deploy --fail-level WARNING

echo "==> Backing up the database before migrating"
as_app .venv/bin/python manage.py backup_db --dir "$BACKUP_DIR" --keep 14

echo "==> Applying migrations"
as_app .venv/bin/python manage.py migrate --noinput

echo "==> Collecting static files"
as_app .venv/bin/python manage.py collectstatic --noinput

echo "==> Restarting the app"
systemctl restart shop2
sleep 2
if systemctl is-active --quiet shop2; then
    echo "OK: shop2 is running"
else
    echo "shop2 failed to start; see: journalctl -u shop2 -n 50" >&2
    exit 1
fi
