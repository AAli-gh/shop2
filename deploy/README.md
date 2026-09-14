# راه‌اندازی روی سرور (Ubuntu 22.04 / 24.04)

این راهنما یک سرور تازه را تا سایت HTTPS آماده می‌کند: PostgreSQL، gunicorn با systemd، nginx و گواهی Let's Encrypt، به‌علاوه زمان‌بندی لغو سفارش‌های پرداخت‌نشده و بکاپ روزانه.

در همه دستورها `shop.example.com` را با دامنه خودتان عوض کنید. پیشنهاد: سرور مجازی ایرانی، تا اتصال به درگاه بانکی و سامانه پیامک از نظر IP مشکلی نداشته باشد.

| فایل | کاربرد |
|---|---|
| `shop2.service` | اجرای برنامه با gunicorn روی سوکت `/run/shop2/gunicorn.sock` |
| `shop2-expire-orders.service` + `.timer` | لغو سفارش‌های پرداخت‌نشده هر ۱۰ دقیقه |
| `shop2-backup.service` + `.timer` | بکاپ روزانه دیتابیس ساعت ۳:۳۰ در `/var/backups/shop2` |
| `nginx-shop2.conf` | HTTPS، هدایت www و http، سرو static و media |
| `deploy.sh` | به‌روزرسانی‌های بعدی سایت با یک دستور |

## ۱. بسته‌ها

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev build-essential git nginx postgresql certbot
```

## ۲. کاربر و پوشه‌ها

```bash
sudo adduser --system --group --home /srv/shop2 shop2
sudo mkdir -p /var/backups/shop2 && sudo chown shop2:shop2 /var/backups/shop2
```

## ۳. دیتابیس

کاربر لینوکسی `shop2` بدون رمز (peer) به دیتابیس هم‌نام وصل می‌شود:

```bash
sudo -u postgres createuser shop2
sudo -u postgres createdb -O shop2 shop2
```

## ۴. کد و محیط پایتون

مخزن باید از روی سرور قابل دریافت باشد (برای مخزن خصوصی، یک deploy key برای کاربر `shop2` بسازید).

```bash
sudo -u shop2 git clone <آدرس-مخزن> /srv/shop2
sudo -u shop2 python3 -m venv /srv/shop2/.venv
sudo -u shop2 /srv/shop2/.venv/bin/pip install -r /srv/shop2/requirements-prod.txt
```

## ۵. فایل `.env`

```bash
sudo -u shop2 cp /srv/shop2/.env.example /srv/shop2/.env
sudo chmod 600 /srv/shop2/.env
python3 -c "import secrets; print(secrets.token_urlsafe(50))"   # مقدار DJANGO_SECRET_KEY
sudo -u shop2 nano /srv/shop2/.env
```

مقادیر لازم (بدون کوتیشن بنویسید؛ systemd هم همین فایل را می‌خواند):

```env
DJANGO_SECRET_KEY=<خروجی دستور بالا>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=shop.example.com,www.shop.example.com
SITE_URL=https://shop.example.com
DJANGO_DB=postgres
DATABASE_URL=postgres:///shop2

EMAIL_HOST=...
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
DEFAULT_FROM_EMAIL=no-reply@shop.example.com

SMS_BACKEND=apps.common.sms.SmsIrBackend
SMSIR_API_KEY=...
SMSIR_OTP_TEMPLATE_ID=...
SMSIR_LINE_NUMBER=...

PAYMENT_GATEWAY=apps.payments.gateways.ZarinPalGateway
ZARINPAL_MERCHANT_ID=...
ZARINPAL_SANDBOX=False
```

تا درگاه واقعی آماده نشده، برای سرور آزمایشی به‌جای دو خط آخر: `ALLOW_MOCK_GATEWAY=True`.

## ۶. آماده‌سازی برنامه

```bash
cd /srv/shop2
sudo -u shop2 env DJANGO_SETTINGS_MODULE=config.settings.prod .venv/bin/python manage.py check --deploy
sudo -u shop2 env DJANGO_SETTINGS_MODULE=config.settings.prod .venv/bin/python manage.py migrate
sudo -u shop2 env DJANGO_SETTINGS_MODULE=config.settings.prod .venv/bin/python manage.py collectstatic --noinput
sudo -u shop2 env DJANGO_SETTINGS_MODULE=config.settings.prod .venv/bin/python manage.py setup_groups
sudo -u shop2 env DJANGO_SETTINGS_MODULE=config.settings.prod .venv/bin/python manage.py createsuperuser
```

گذرواژه ادمین سرور را جدید و قوی انتخاب کنید (از حساب توسعه استفاده نکنید).

## ۷. سرویس‌ها

```bash
sudo cp /srv/shop2/deploy/*.service /srv/shop2/deploy/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now shop2 shop2-expire-orders.timer shop2-backup.timer
systemctl status shop2
systemctl list-timers 'shop2-*'
```

## ۸. گواهی HTTPS و nginx

دامنه باید پیش از این مرحله به IP سرور اشاره کند.

```bash
sudo systemctl stop nginx
sudo certbot certonly --standalone -d shop.example.com -d www.shop.example.com \
     --pre-hook "systemctl stop nginx" --post-hook "systemctl start nginx"

sudo cp /srv/shop2/deploy/nginx-shop2.conf /etc/nginx/sites-available/shop2
sudo sed -i 's/shop.example.com/<دامنه-شما>/g' /etc/nginx/sites-available/shop2
sudo ln -s /etc/nginx/sites-available/shop2 /etc/nginx/sites-enabled/shop2
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl start nginx
```

تمدید گواهی خودکار است (`certbot.timer`)؛ hookهای بالا ذخیره شده‌اند و nginx را برای تمدید موقتاً متوقف می‌کنند.

## ۹. فایروال

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

## به‌روزرسانی‌های بعدی

```bash
sudo /srv/shop2/deploy/deploy.sh
```

کد را می‌گیرد، وابستگی‌ها را نصب می‌کند، تنظیمات را بررسی می‌کند، **پیش از migrate بکاپ می‌گیرد**، static را جمع می‌کند و سرویس را ری‌استارت می‌کند.

## نگهداری

- **لاگ برنامه:** `journalctl -u shop2 -f` و فایل‌های `/srv/shop2/logs/`
- **لاگ لغو سفارش‌ها و بکاپ:** `journalctl -u shop2-expire-orders` و `journalctl -u shop2-backup`
- **بکاپ خارج از سرور:** بکاپ‌ها روی همان سرورند؛ پوشه `/var/backups/shop2` و `/srv/shop2/media` را مرتب به جای دیگری کپی کنید (مثلاً با `rsync` یا `rclone` به فضای ذخیره‌سازی ابری).
- **بازگردانی بکاپ PostgreSQL:** بسته به فرمت فایل خروجی `backup_db`، با `psql` یا `pg_restore` روی یک دیتابیس خالی.
