"""The Liara (PaaS) deployment files — see deploy/README-liara.md.

Liara's filesystem is read-only apart from /tmp, so the app must boot without creating any
directory of its own, and its nginx must accept uploads bigger than the 1 MB default.
"""
import json
from pathlib import Path

from django.conf import settings

from apps.common.test_prod_settings import run_python

BASE = Path(settings.BASE_DIR)


def test_liara_json_describes_a_django_app():
    config = json.loads((BASE / "liara.json").read_text(encoding="utf-8"))
    assert config["platform"] == "django"
    assert config["port"] == 8000


def test_nginx_accepts_review_photos_and_product_imports():
    conf = (BASE / "liara_nginx.conf").read_text(encoding="utf-8")
    assert "client_max_body_size 32M;" in conf
    assert "/usr/src/app/media" in conf
    assert "/usr/src/app/staticfiles" in conf


def test_deployment_leaves_out_secrets_and_local_data():
    ignored = {line.strip() for line in (BASE / ".liaraignore").read_text(encoding="utf-8").splitlines()}
    for entry in (".env", "db.sqlite3", "media/", "logs/", "backups/", ".venv/", "staticfiles/", "tools/"):
        assert entry in ignored, entry


def test_hooks_are_unix_shell_scripts_that_set_the_app_up():
    pre_start = (BASE / "liara_pre_start.sh").read_text(encoding="utf-8")
    post_build = (BASE / "liara_post_build.sh").read_text(encoding="utf-8")
    for script in (pre_start, post_build):
        assert script.startswith("#!/bin/bash")
        assert "\r\n" not in script  # Liara runs them on Linux
    assert "manage.py migrate" in pre_start
    assert "manage.py collectstatic" in post_build


def test_static_storage_can_drop_the_manifest_for_a_paas():
    """Liara collects static files itself and produces no manifest, so the plain backend is used."""
    code = (
        "import django, json; django.setup(); from django.conf import settings as s; "
        "print(json.dumps(s.STORAGES['staticfiles']['BACKEND']))"
    )
    plain = "django.contrib.staticfiles.storage.StaticFilesStorage"

    default = run_python(["-c", code])
    chosen = run_python(["-c", code], DJANGO_STATICFILES_STORAGE=plain)

    assert json.loads(default.stdout.strip().splitlines()[-1]).endswith("ManifestStaticFilesStorage")
    assert json.loads(chosen.stdout.strip().splitlines()[-1]) == plain


def test_the_app_boots_on_a_read_only_filesystem(tmp_path):
    """With DJANGO_LOG_TO_STDOUT the app logs to the platform and creates no directories."""
    missing = tmp_path / "read-only" / "logs"
    code = (
        "import django, json, logging; django.setup(); from django.conf import settings as s; "
        "print(json.dumps({'handler': type(logging.getLogger('shop').handlers[0]).__name__, "
        "'cache': s.CACHES['default'].get('LOCATION', '')}))"
    )
    result = run_python(
        ["-c", code],
        DJANGO_LOG_TO_STDOUT="True",
        DJANGO_LOG_DIR=str(missing),
        DJANGO_CACHE_DIR=str(tmp_path / "cache"),
    )

    assert result.returncode == 0, result.stderr
    values = json.loads(result.stdout.strip().splitlines()[-1])
    assert values["handler"] == "StreamHandler"
    assert values["cache"] == str(tmp_path / "cache")
    assert not missing.exists()  # nothing was written to the read-only path
