# راه‌اندازی روی لیارا (Liara)

لیارا هاست ابری است و سرور را خودش مدیریت می‌کند. اگر به‌جای سرور مجازی، لیارا را انتخاب کرده‌اید، این راهنما را دنبال کنید و `README.md` کنار آن را (که برای سرور مجازی و nginx است) نادیده بگیرید.

| فایل | کاربرد |
|---|---|
| `liara.json` | نوع برنامه (Django)، شناسه برنامه و پورت |
| `liara_nginx.conf` | افزایش حد آپلود از ۱ مگابایت به ۳۲ مگابایت و سرو کردن `media/` و `static/` |
| `liara_post_build.sh` | ساخت فایل‌های static هنگام استقرار |
| `liara_pre_start.sh` | اجرای migrationها و ساخت گروه‌های دسترسی در هر بار اجرا |
| `.liaraignore` | فایل‌هایی که آپلود نمی‌شوند (`.env`، دیتابیس محلی، عکس‌ها، لاگ‌ها) |

## ۱. ساخت برنامه و دیتابیس

در پنل لیارا:

1. **پلتفرم ← ایجاد برنامه**، نوع **Django**. شناسهٔ برنامهٔ فعلی `djangoshop` است و در `liara.json` هم همین نوشته شده؛ اگر برنامهٔ دیگری ساختید، شناسه را در آن فایل عوض کنید.
2. **دیتابیس ← PostgreSQL** نسخهٔ ۱۷. همان شبکهٔ خصوصی برنامه را انتخاب کنید.
3. **دیسک** برای عکس‌ها: در بخش دیسک‌های برنامه یک دیسک با نام `media` بسازید (مثلاً ۵ گیگابایت) و هنگام استقرار آن را به مسیر `media/` وصل کنید.

> فایل‌سیستم لیارا فقط‌خواندنی است. عکس‌های محصولات فقط روی دیسک می‌مانند؛ بدون دیسک با هر استقرار پاک می‌شوند.

## ۲. متغیرهای محیطی

در بخش **متغیرها**ی برنامه این مقادیر را وارد کنید (مقدارهای نمونه را با مقادیر خودتان عوض کنید):

```env
DJANGO_SETTINGS_MODULE=config.settings.prod
DJANGO_SECRET_KEY=<۵۰ نویسه تصادفی>
DJANGO_ALLOWED_HOSTS=shop2.liara.run,shop.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://shop2.liara.run,https://shop.example.com
SITE_URL=https://shop.example.com

DJANGO_DB=postgres
DATABASE_URL=<آدرس اتصال دیتابیس از پنل لیارا>

# فایل‌سیستم فقط‌خواندنی است: لاگ‌ها به کنسول لیارا می‌روند و کش در tmp نوشته می‌شود
DJANGO_LOG_TO_STDOUT=True
DJANGO_CACHE_DIR=/tmp/shop2-cache
RATELIMIT_IP_HEADER=HTTP_X_FORWARDED_FOR

# آدرس غیرقابل‌حدس پنل مدیریت (بدون آن، بررسی استقرار خطا می‌دهد)
ADMIN_URL=panel-<چند حرف تصادفی>/

SMS_BACKEND=apps.common.sms.SmsIrBackend
SMSIR_API_KEY=<کلید SMS.ir>
SMSIR_OTP_TEMPLATE_ID=<شناسه قالب Verify>
SMSIR_LINE_NUMBER=<شماره خط>

PAYMENT_GATEWAY=apps.payments.gateways.ZarinPalGateway
ZARINPAL_MERCHANT_ID=<کد مرچنت>
ZARINPAL_SANDBOX=False

EMAIL_HOST=<سرور SMTP>
EMAIL_HOST_USER=<نام کاربری>
EMAIL_HOST_PASSWORD=<گذرواژه>
DEFAULT_FROM_EMAIL=no-reply@shop.example.com
ADMIN_EMAIL=admin@shop.example.com
ORDER_NOTIFY_PHONES=09120000000
```

تا وقتی درگاه یا سامانهٔ پیامک واقعی آماده نیست، برای نسخهٔ آزمایشی به‌جای مقادیر بالا `ALLOW_MOCK_GATEWAY=True` و `ALLOW_FAKE_SMS=True` بگذارید.

کلید تصادفی را با این دستور بسازید:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

### قالب‌های پیامک (Verify)

پیامک‌هایی که از خط فرستاده می‌شوند به شماره‌هایی که تبلیغات را بسته‌اند (لیست سیاه مخابرات) نمی‌رسند؛ پیامک با **قالب Verify** می‌رسد. برای هر اطلاع‌رسانی در پنل SMS.ir (بخش ارسال سریع / قالب‌ها) یک قالب بسازید و پس از تأیید، شناسه‌اش را در متغیر گفته‌شده بگذارید. رویدادی که شناسه نداشته باشد مثل قبل از خط فرستاده می‌شود.

| متغیر | پارامترها | متن پیشنهادی قالب |
|---|---|---|
| `SMSIR_OTP_TEMPLATE_ID` | `#CODE#` | کد ورود شما: #CODE# |
| `SMSIR_TEMPLATE_ORDER_PLACED` | `#ORDER#` `#AMOUNT#` | سفارش #ORDER# ثبت شد. مبلغ: #AMOUNT# تومان |
| `SMSIR_TEMPLATE_ORDER_STATUS` | `#ORDER#` `#STATUS#` | وضعیت سفارش #ORDER#: #STATUS# |
| `SMSIR_TEMPLATE_RETURN_STATUS` | `#ORDER#` `#STATUS#` | درخواست مرجوعی سفارش #ORDER#: #STATUS# |
| `SMSIR_TEMPLATE_ORDER_PAID_STAFF` | `#ORDER#` `#AMOUNT#` | سفارش جدید #ORDER# به مبلغ #AMOUNT# تومان پرداخت شد |
| `SMSIR_TEMPLATE_LOW_STOCK` | `#PRODUCT#` `#COUNT#` | کمبود موجودی: #PRODUCT# — #COUNT# عدد مانده |
| `SMSIR_TEMPLATE_CART_REMINDER` | `#COUNT#` | #COUNT# کالا در سبد خرید شما منتظر است |
| `SMSIR_TEMPLATE_PRICE_DROP` | `#PRODUCT#` `#PRICE#` | قیمت «#PRODUCT#» به #PRICE# تومان کاهش یافت |
| `SMSIR_TEMPLATE_QUESTION_ANSWERED` | `#PRODUCT#` | به پرسش شما درباره «#PRODUCT#» پاسخ داده شد |
| `SMSIR_TEMPLATE_REVIEW_REQUEST` | `#PRODUCT#` | از «#PRODUCT#» راضی بودید؟ نظرتان را در سایت ثبت کنید |
| `SMSIR_TEMPLATE_WINBACK` | `#CODE#` `#PERCENT#` `#DAYS#` | دلمان برایتان تنگ شده! با کد #CODE# تا #DAYS# روز #PERCENT# درصد تخفیف بگیرید |

- نام پارامترها باید دقیقاً همین‌ها باشد (حروف بزرگ). نام فروشگاه و آدرس سایت را در خود متن قالب بنویسید.
- مقدار هر پارامتر حداکثر ۲۵ نویسه فرستاده می‌شود؛ نام‌های طولانی محصول کوتاه می‌شوند.
- قالب‌های «سبد رهاشده» و «کاهش قیمت» جنبهٔ تبلیغی دارند و ممکن است SMS.ir تأییدشان نکند؛ در آن صورت همان پیامک خط فرستاده می‌شود.

## ۳. استقرار

با Liara CLI (پیشنهادی، چون `.liaraignore` را رعایت می‌کند):

```bash
npm install -g @liara/cli
liara login
liara deploy --app djangoshop --disks media:media
```

> گزینهٔ `--disks media:media` را در **هر** استقرار بنویسید؛ دیسک عکس‌ها را به پوشهٔ `media/` وصل می‌کند. بدون آن، آپلود عکس محصول روی فایل‌سیستم فقط‌خواندنی خطا می‌دهد.

یا از پنل: پوشهٔ پروژه را zip کنید و در بخش «استقرار جدید» بارگذاری کنید. در این حالت فایل‌های `.venv`، `db.sqlite3`، `media/`، `logs/` و `.env` را خودتان از zip حذف کنید.

هنگام استقرار، لیارا این کارها را انجام می‌دهد: نصب بسته‌های `requirements.txt`، ساخت فایل‌های static (`liara_post_build.sh`) و اجرای migrationها پیش از بالا آمدن برنامه (`liara_pre_start.sh`).

## ۴. کاربر مدیر

پس از اولین استقرار، از بخش **کنسول** برنامه در پنل لیارا:

```bash
python manage.py createsuperuser
```

بعد طبق راهنمای `README.md` (بخش ورود دومرحله‌ای) شمارهٔ موبایل مدیر را از سایت تأیید کنید.

## ۵. زمان‌بندی کارها (Cron)

در **تنظیمات برنامه ← Cron Job** این موارد را اضافه کنید:

| زمان‌بندی | دستور | کار |
|---|---|---|
| `*/10 * * * *` | `python manage.py expire_unpaid_orders` | لغو سفارش‌های پرداخت‌نشده و آزادسازی موجودی |
| `15 9-21 * * *` | `python manage.py remind_abandoned_carts` | یادآوری سبد رهاشده |
| `20 9-21 * * *` | `python manage.py send_price_alerts` | خبر کاهش قیمت |
| `25 9-21 * * *` | `python manage.py request_reviews` | درخواست نظر از مشتریانی که سفارششان تحویل شده |
| `0 11 * * *` | `python manage.py send_winback` | کد تخفیف برای مشتریان خوابیده (فقط وقتی در تنظیمات سایت روشن باشد) |

## ۶. دامنه و پشتیبان‌گیری

- **دامنه:** بخش «دامنه‌ها»ی برنامه، دامنه را اضافه و رکوردهای DNS را طبق راهنمای لیارا تنظیم کنید؛ سپس گواهی SSL رایگان را فعال کنید. بعد از اتصال دامنه، `DJANGO_ALLOWED_HOSTS`، `DJANGO_CSRF_TRUSTED_ORIGINS` و `SITE_URL` را به‌روز کنید.
- **پشتیبان‌گیری:** از بخش «پشتیبان‌گیری» دیتابیس، نسخهٔ خودکار روزانه را فعال کنید. دیسک `media` هم پشتیبان‌گیری جدا دارد. دستور `backup_db` پروژه برای سرور مجازی است و روی لیارا لازم نیست.

## تفاوت‌ها با سرور مجازی

- لاگ‌های سایت به‌جای پوشهٔ `logs/` در بخش «گزارشات» پنل لیارا دیده می‌شوند؛ صفحهٔ `/logs/` سایت روی لیارا خالی است.
- شمارش محدودیت تلاش‌ها (کش) در `/tmp` ذخیره می‌شود و با هر استقرار صفر می‌شود.
- تنظیمات nginx و systemd پوشهٔ `deploy/` روی لیارا استفاده نمی‌شوند.
