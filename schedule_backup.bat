@echo off
rem Daily database backup — schedule with (once, admin not required):
rem   schtasks /Create /TN "shop2-backup" /TR "D:\Ali\shop2\schedule_backup.bat" /SC DAILY /ST 03:30
rem Show existing task: schtasks /Query /TN "shop2-backup"
rem Remove:              schtasks /Delete /TN "shop2-backup" /F
cd /d "%~dp0"
.venv\Scripts\python.exe manage.py backup_db --keep 14 >> backups\backup.log 2>&1
