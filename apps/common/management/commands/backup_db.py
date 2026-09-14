"""Daily database backup.

SQLite: copies the database file (with WAL checkpoint).
Postgres: shells out to pg_dump.

Keeps the newest KEEP_BACKUPS files in the backup directory (default: BASE_DIR/backups).
Usage:
    python manage.py backup_db
    python manage.py backup_db --dir D:\backups --keep 30
Schedule daily via Windows Task Scheduler or cron:
    <venv>\Scripts\python.exe manage.py backup_db
"""
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Back up the database and prune old backups."

    def add_arguments(self, parser):
        parser.add_argument("--dir", default=None, help="Backup directory (default: BASE_DIR/backups)")
        parser.add_argument("--keep", type=int, default=14, help="How many backups to keep")

    def handle(self, *args, **options):
        backup_dir = Path(options["dir"] or (settings.BASE_DIR / "backups"))
        backup_dir.mkdir(parents=True, exist_ok=True)
        keep = max(options["keep"], 1)

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        engine = settings.DATABASES["default"]["ENGINE"]

        if "sqlite" in engine:
            dest = backup_dir / f"db-{stamp}.sqlite3"
            self._sqlite_backup(settings.DATABASES["default"]["NAME"], dest)
        elif "postgres" in engine:
            dest = backup_dir / f"db-{stamp}.sql"
            self._pg_backup(settings.DATABASES["default"], dest)
        else:
            self.stderr.write(f"Unsupported engine: {engine}")
            return

        pruned = self._prune(backup_dir, keep)
        self.stdout.write(self.style.SUCCESS(f"Backup written: {dest}"))
        if pruned:
            self.stdout.write(f"Pruned {pruned} old backup(s).")

    def _sqlite_backup(self, src, dest):
        from django.db import connection

        # WAL checkpoint so the copied file is consistent
        with connection.cursor() as cur:
            cur.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        shutil.copy2(src, dest)

    def _pg_backup(self, db_config, dest):
        env = {
            "PGPASSWORD": db_config.get("PASSWORD", ""),
            "PATH": subprocess.os.environ.get("PATH", ""),
        }
        cmd = [
            "pg_dump",
            "--host", db_config.get("HOST") or "localhost",
            "--port", str(db_config.get("PORT") or 5432),
            "--username", db_config.get("USER") or "",
            "--no-password",
            "--clean",
            "--file", str(dest),
            db_config.get("NAME") or "",
        ]
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"pg_dump failed: {result.stderr.strip()}")

    def _prune(self, backup_dir: Path, keep: int) -> int:
        backups = sorted(
            [p for p in backup_dir.glob("db-*") if p.is_file()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        removed = 0
        for old in backups[keep:]:
            old.unlink()
            removed += 1
        return removed
