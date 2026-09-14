@echo off
rem Cancel unpaid orders past the payment window — schedule every 10 minutes (once):
rem   schtasks /Create /TN "shop2-expire-orders" /TR "D:\Ali\shop2\schedule_expire_orders.bat" /SC MINUTE /MO 10
rem Show existing task: schtasks /Query /TN "shop2-expire-orders"
rem Remove:              schtasks /Delete /TN "shop2-expire-orders" /F
cd /d "%~dp0"
.venv\Scripts\python.exe manage.py expire_unpaid_orders >> logs\expire_orders.log 2>&1
