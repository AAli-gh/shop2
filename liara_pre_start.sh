#!/bin/bash
# Runs on every start, with the app's environment variables available (Liara hook).
set -e

echo "shop2: applying database migrations"
python manage.py migrate --noinput

echo "shop2: creating the staff permission groups"
python manage.py setup_groups

echo "shop2: pre-start finished"
