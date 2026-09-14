# فروشگاه shop2

فروشگاه اینترنتی محصولات فیزیکی با جنگو — رابط فارسی و راست‌به‌چپ.

## استک

- **Backend:** Django 5.2 + Django REST Framework، لایه سرویس (`services.py` در هر اپ)
- **Frontend:** Django Templates + Tailwind CSS v4 (standalone CLI) + HTMX 2 + Vanilla JS
- **DB:** SQLite در توسعه (سوییچ به PostgreSQL با متغیر محیطی `DJANGO_DB=postgres`)
- **پرداخت:** درگاه شبیه‌ساز (Mock) — جایگزینی با زرین‌پال فقط با ساخت یک کلاس و تغییر env

## راه‌اندازی

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
copy .env.example .env
.venv/Scripts/python manage.py migrate
.venv/Scripts/python manage.py createsuperuser
.venv/Scripts/python manage.py runserver
```

ساخت CSS (Tailwind):

```bash
build_css.bat        # build یک‌باره
build_css.bat watch  # watch در حین توسعه
```

> فایل `tools/tailwindcss.exe` را از [releases تیلویند](https://github.com/tailwindlabs/tailwindcss/releases) دانلود و در `tools/` قرار دهید (gitignore شده). خروجی ساخته‌شده (`static/css/site.css`) کامیت می‌شود، پس بدون exe هم سایت بالا می‌آید.

## اپ‌ها

| اپ | وظیفه |
|---|---|
| `common` | SiteSettings ( singleton)، تمپلیت‌تگ‌های فارسی (`jalali`, `fa_digits`, `toman`) |
| `accounts` | کاربر با ایمیل (USERNAME_FIELD)، آدرس‌های ذخیره‌شده |
| `catalog` | دسته‌بندی، محصول، گالری، جستجو/فیلتر/مرتب‌سازی |
| `cart` | سبد مهمان (session) + کاربر؛ ادغام خودکار هنگام ورود |
| `discounts` | کوپن درصدی/مبلغی با سقف، حداقل سفارش، محدودیت مصرف |
| `orders` | چک‌اوت، `place_order` اتمیک (رزرو موجودی + قفل کوپن)، تاریخچه سفارش |
| `payments` | `PaymentGateway` ABC + `MockGateway`؛ پرداخت شبیه‌سازی‌شده |
| `reviews` | نظر ۱–۵ ستاره، یک نظر per user، تعدیل با ادمین |

## سوییچ به PostgreSQL

```env
DJANGO_DB=postgres
DATABASE_URL=postgres://user:pass@localhost:5432/shop2
```

## جایگزینی درگاه پرداخت

1. کلاس جدید در `apps/payments/gateways.py` بسازید که `PaymentGateway` را implement کند:
   - `request_payment(order) -> url`
   - `verify(order) -> PaymentResult`
2. در `.env`: `PAYMENT_GATEWAY=apps.payments.gateways.ZarinPalGateway`

بدون تغییر هیچ کد دیگری.

## تست‌ها

```bash
.venv/Scripts/python -m pytest apps -q
```

تست سرویس‌ها، پرداخت (Mock و زرین‌پال با پاسخ ساختگی)، لغو و انقضای سفارش، محدودیت تلاش و تنظیمات production.

## راه‌اندازی روی سرور (production)

تنظیمات production در `config/settings/prod.py` است و همه چیز را از متغیرهای محیطی می‌خواند؛ اگر مقدار ضروری نباشد یا ناامن باشد (کلید کوتاه، `DJANGO_ALLOWED_HOSTS` خالی، `EMAIL_HOST` خالی، درگاه Mock) سایت اصلاً بالا نمی‌آید. فهرست متغیرها در `.env.example`.

```bash
export DJANGO_SETTINGS_MODULE=config.settings.prod   # wsgi/asgi به‌طور پیش‌فرض همین را دارند؛ برای manage.py لازم است
pip install -r requirements.txt gunicorn
python manage.py check --deploy
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 3
```

nginx جلوی gunicorn (فایل‌های static/media را خودش سرو می‌کند و IP واقعی را برای محدودیت تلاش می‌فرستد):

```nginx
location /static/ { alias /srv/shop2/staticfiles/; }
location /media/  { alias /srv/shop2/media/; }
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Real-IP $remote_addr;
}
```

**لغو خودکار سفارش‌های پرداخت‌نشده** — هر ۱۰ دقیقه اجرا شود (مهلت: `ORDER_PAYMENT_TIMEOUT_MINUTES`، پیش‌فرض ۳۰):

```bash
*/10 * * * * cd /srv/shop2 && DJANGO_SETTINGS_MODULE=config.settings.prod .venv/bin/python manage.py expire_unpaid_orders
```

روی ویندوز: `schedule_expire_orders.bat` (دستور schtasks داخل فایل).

**ورود با موبایل (پیامک)** — صفحه `/accounts/login/` با کد یک‌بارمصرف؛ ورود با ایمیل در `/accounts/login/email/`. در توسعه پیامک‌ها به‌جای ارسال در `sent_sms/` نوشته می‌شوند. برای SMS.ir در پنل یک قالب Verify با پارامتر `CODE` بسازید و در `.env` بگذارید:

```env
SMS_BACKEND=apps.common.sms.SmsIrBackend
SMSIR_API_KEY=...
SMSIR_OTP_TEMPLATE_ID=...
SMSIR_LINE_NUMBER=...   # برای پیامک وضعیت سفارش
```

## نکات مهم

- **قیمت‌ها:** تومان صحیح (بدون اعشار). اسنپ‌شات قیمت در `OrderItem`.
- **موجودی:** رزرو هنگام ثبت سفارش با UPDATE شرطی (`stock__gte=qty`) — امن روی SQLite و Postgres.
- **کوپن:** افزایش `used_count` با UPDATE شرطی داخل تراکنش ثبت سفارش — بدون رقابت.
- **سفارش بی‌پرداخت:** موجودی رزرو می‌ماند تا کاربر لغو کند یا `expire_unpaid_orders` بعد از مهلت پرداخت لغوش کند (بازگشت موجودی + کوپن). سفارشی که پرداختش در ۱۵ دقیقه اخیر شروع شده لغو نمی‌شود؛ پرداختِ رسیده برای سفارش لغوشده verify نمی‌شود تا بانک خودش مبلغ را برگرداند.
- **لغو از ادمین:** موجودی و کوپن برمی‌گردد؛ مبلغ پرداخت‌شده از کیف پول خودکار به کیف پول برمی‌گردد؛ پرداخت آنلاین باید دستی بازگردانده شود (هشدار در ادمین + `REFUND_REQUIRED` در لاگ).
- **محدودیت تلاش:** `apps/common/ratelimit.py` روی ورود، ثبت‌نام، بازیابی رمز، کد تخفیف، کد هدیه، خبرنامه، خبرم‌کن، نظر و تماس؛ پاسخ ۴۲۹. در production کش باید بین workerها مشترک باشد (پیش‌فرض: کش فایلی).
- **تاریخ:** ذخیره UTC، نمایش جلالی با فیلتر `jalali`.
