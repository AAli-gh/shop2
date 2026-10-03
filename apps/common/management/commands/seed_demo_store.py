"""Fill a demo store with complete-looking content: products with pictures, specs and full
descriptions, colour variants, discounts, reviews, answered questions, blog posts, info pages,
banners, shipping methods and a welcome coupon.

    python manage.py seed_demo_store            # add the demo content (safe to re-run)
    python manage.py seed_demo_store --clear    # remove the demo reviewers and their reviews/questions

All pictures are drawn by apps.common.demo_images. Reviews and questions belong to demo accounts
whose e-mail ends in @demo.invalid (no password, can't sign in): remove them with --clear before the
shop sells for real.
"""
import random
from datetime import timedelta

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.common import demo_images as art

DEMO_DOMAIN = "@demo.invalid"
M = 1_000_000

# category -> (shape for products without one, [(spec name, unit)])
CATEGORIES = {
    "یخچال و فریزر": ("fridge", []),
    "ماشین لباسشویی": ("washer", []),
    "ماشین ظرفشویی": ("dishwasher", []),
    "گاز و اجاق": ("stove", []),
    "جاروبرقی": ("vacuum", []),
    "لوازم آشپزخانه": ("airfryer", []),
    "تلویزیون": ("tv", [("اندازه صفحه", "اینچ"), ("کیفیت تصویر", ""), ("هوشمند", ""), ("نوع پنل", "")]),
    "کولر گازی": ("ac", [("ظرفیت", "BTU"), ("کمپرسور", ""), ("رده انرژی", ""), ("نوع", "")]),
}

BRANDS = [("پاکشوما", "ایران"), ("امرسان", "ایران"), ("هایسنس", "چین"), ("تی‌سی‌ال", "چین"), ("گری", "چین")]

# (brand, category, name, price, sale, stock, shape, finish, specs, colours[(name, hex, finish, stock)])
PRODUCTS = [
    ("سامسونگ", "یخچال و فریزر", "یخچال فریزر سامسونگ مدل RT۳۲ دو درب", 38 * M, 35_900_000, 6, "fridge", "steel",
     {"ظرفیت": "560", "تعداد درب": "دو درب", "رده انرژی": "A++", "کمپرسور": "اینورتر", "فریزر": "بالا"},
     [("استیل", "#9aa3ad", "steel", 4), ("سفید", "#f4f5f7", "white", 2)]),
    ("ال‌جی", "یخچال و فریزر", "یخچال ساید بای ساید ال‌جی ۷۰۰ لیتری", 89 * M, None, 2, "side_by_side", "silver",
     {"ظرفیت": "700", "تعداد درب": "دو درب ساید", "رده انرژی": "A++", "کمپرسور": "اینورتر", "فریزر": "ساید"}, []),
    ("امرسان", "یخچال و فریزر", "یخچال تک درب امرسان ۱۲ فوت", 17_500_000, 16_400_000, 9, "fridge", "white",
     {"ظرفیت": "330", "تعداد درب": "تک درب", "رده انرژی": "A+", "کمپرسور": "معمولی", "فریزر": "داخلی"}, []),
    ("هایسنس", "یخچال و فریزر", "یخچال فریزر پایین هایسنس ۲۶ فوت", 46 * M, 42_500_000, 4, "fridge", "black",
     {"ظرفیت": "610", "تعداد درب": "دو درب", "رده انرژی": "A+", "کمپرسور": "اینورتر", "فریزر": "پایین"}, []),
    ("پاکشوما", "ماشین لباسشویی", "لباسشویی پاکشوما ۷ کیلویی", 15_900_000, None, 11, "washer", "white",
     {"ظرفیت": "7", "دور موتور": "1000", "تعداد برنامه": "12", "رنگ": "سفید"}, []),
    ("ال‌جی", "ماشین لباسشویی", "لباسشویی ال‌جی ۱۰ کیلویی دایرکت درایو", 42 * M, 38_900_000, 5, "washer", "silver",
     {"ظرفیت": "10", "دور موتور": "1400", "تعداد برنامه": "14", "رنگ": "نقره‌ای"},
     [("نقره‌ای", "#c4cad2", "silver", 3), ("مشکی", "#2b2e34", "black", 2)]),
    ("سامسونگ", "ماشین لباسشویی", "لباسشویی سامسونگ ۹ کیلویی ادواش", 36_500_000, None, 3, "washer", "black",
     {"ظرفیت": "9", "دور موتور": "1400", "تعداد برنامه": "16", "رنگ": "مشکی"}, []),
    ("اسنوا", "ماشین ظرفشویی", "ظرفشویی اسنوا ۱۳ نفره", 21 * M, 19_800_000, 7, "dishwasher", "white",
     {"تعداد سرویس": "13", "برنامه شستشو": "6", "مصرف آب": "11"}, []),
    ("ال‌جی", "ماشین ظرفشویی", "ظرفشویی ال‌جی ۱۴ نفره استیم", 39 * M, 36_500_000, 3, "dishwasher", "steel",
     {"تعداد سرویس": "14", "برنامه شستشو": "10", "مصرف آب": "9"}, []),
    ("استرلین", "گاز و اجاق", "اجاق گاز رومیزی استرلین پنج شعله", 9_800_000, 8_900_000, 14, "stove", "black",
     {"تعداد شعله": "5", "جنس صفحه": "شیشه", "ولوم": "فندکی"}, []),
    ("بوش", "گاز و اجاق", "اجاق گاز بوش چهار شعله استیل", 16 * M, None, 5, "stove", "steel",
     {"تعداد شعله": "4", "جنس صفحه": "استیل", "ولوم": "فندکی ایمنی‌دار"}, []),
    ("پارس", "جاروبرقی", "جاروبرقی پارس ۲۲۰۰ وات بدون کیسه", 7_400_000, 6_900_000, 18, "vacuum", "red",
     {"توان": "2200", "مخزن": "3", "نوع": "سطلی"}, []),
    ("بوش", "جاروبرقی", "جاروبرقی بوش ۲۴۰۰ وات", 14_500_000, None, 6, "vacuum", "silver",
     {"توان": "2400", "مخزن": "4", "نوع": "کیسه‌ای"}, []),
    ("جی‌پلاس", "لوازم آشپزخانه", "سرخ‌کن بدون روغن جی‌پلاس ۵ لیتری", 5_900_000, 5_200_000, 22, "airfryer", "black",
     {"توان": "1400", "ظرفیت": "5", "نوع": "سرخ‌کن بدون روغن"}, []),
    ("سامسونگ", "لوازم آشپزخانه", "مایکروویو سامسونگ ۳۲ لیتری", 13 * M, 11_900_000, 8, "microwave", "black",
     {"توان": "1000", "ظرفیت": "32", "نوع": "مایکروویو"}, []),
    ("ال‌جی", "لوازم آشپزخانه", "مایکروویو ال‌جی ۲۵ لیتری گریل‌دار", 9_900_000, None, 10, "microwave", "silver",
     {"توان": "900", "ظرفیت": "25", "نوع": "مایکروویو"}, []),
    ("بوش", "لوازم آشپزخانه", "اسپرسوساز بوش ۱۵ بار", 12_800_000, 11_500_000, 7, "coffee", "black",
     {"توان": "1350", "ظرفیت": "1.4", "نوع": "اسپرسوساز"}, []),
    ("سامسونگ", "تلویزیون", "تلویزیون هوشمند سامسونگ ۵۵ اینچ 4K", 48 * M, 44_900_000, 5, "tv", "black",
     {"اندازه صفحه": "55", "کیفیت تصویر": "4K UHD", "هوشمند": "بله", "نوع پنل": "QLED"}, []),
    ("ال‌جی", "تلویزیون", "تلویزیون ال‌جی ۶۵ اینچ OLED", 129 * M, None, 2, "tv", "black",
     {"اندازه صفحه": "65", "کیفیت تصویر": "4K UHD", "هوشمند": "بله", "نوع پنل": "OLED"}, []),
    ("هایسنس", "تلویزیون", "تلویزیون هایسنس ۴۳ اینچ فول اچ‌دی", 19 * M, 17_500_000, 12, "tv", "black",
     {"اندازه صفحه": "43", "کیفیت تصویر": "Full HD", "هوشمند": "بله", "نوع پنل": "LED"}, []),
    ("تی‌سی‌ال", "تلویزیون", "تلویزیون تی‌سی‌ال ۵۰ اینچ گوگل‌تی‌وی", 27 * M, 24_900_000, 8, "tv", "black",
     {"اندازه صفحه": "50", "کیفیت تصویر": "4K UHD", "هوشمند": "بله", "نوع پنل": "LED"}, []),
    ("گری", "کولر گازی", "کولر گازی گری ۱۲۰۰۰ اینورتر", 32 * M, 29_900_000, 6, "ac", "white",
     {"ظرفیت": "12000", "کمپرسور": "اینورتر", "رده انرژی": "A++", "نوع": "اسپلیت سرد و گرم"}, []),
    ("ال‌جی", "کولر گازی", "کولر گازی ال‌جی ۱۸۰۰۰ دوال اینورتر", 52 * M, None, 3, "ac", "white",
     {"ظرفیت": "18000", "کمپرسور": "دوال اینورتر", "رده انرژی": "A+++", "نوع": "اسپلیت سرد و گرم"}, []),
    ("سامسونگ", "کولر گازی", "کولر گازی سامسونگ ۲۴۰۰۰ ویندفری", 74 * M, 69 * M, 2, "ac", "white",
     {"ظرفیت": "24000", "کمپرسور": "اینورتر", "رده انرژی": "A++", "نوع": "اسپلیت سرد و گرم"}, []),
    ("امرسان", "کولر گازی", "کولر گازی امرسان ۹۰۰۰ معمولی", 19 * M, None, 9, "ac", "white",
     {"ظرفیت": "9000", "کمپرسور": "معمولی", "رده انرژی": "A", "نوع": "اسپلیت فقط سرد"}, []),
]

# category -> (what it does for a home, buying tips, care note)
CATEGORY_COPY = {
    "یخچال و فریزر": ("مواد غذایی را تازه نگه می‌دارد و با چیدمان منظم، دسترسی به همه چیز را آسان می‌کند",
                      "ظرفیت را با تعداد اعضای خانواده بسنجید و پیش از خرید، عرض و ارتفاع جای یخچال را اندازه بگیرید",
                      "یخچال را دست‌کم ۱۰ سانتی‌متر دورتر از دیوار بگذارید تا کمپرسور راحت‌تر نفس بکشد"),
    "ماشین لباسشویی": ("شستشوی روزانه را بی‌دردسر می‌کند و با برنامه‌های متنوع از پارچه‌های ظریف تا ملحفه‌های سنگین را تمیز می‌شوید",
                       "ظرفیت ۷ کیلو برای خانواده‌های کوچک و ۹ کیلو به بالا برای خانواده‌های پرجمعیت مناسب است",
                       "هر چند ماه یک بار برنامه تمیزکردن مخزن را بدون لباس اجرا کنید"),
    "ماشین ظرفشویی": ("در مصرف آب و وقت صرفه‌جویی می‌کند و ظرف‌ها را بهداشتی‌تر از شستشوی دستی تمیز می‌کند",
                      "تعداد سرویس را با تعداد وعده‌های روزانه خانواده هماهنگ کنید",
                      "فیلتر کف دستگاه را هفته‌ای یک بار بشویید"),
    "گاز و اجاق": ("آشپزی روزانه را سریع و دقیق می‌کند",
                   "تعداد شعله و جنس صفحه را با سبک آشپزی و سهولت تمیزکاری مقایسه کنید",
                   "شعله‌پخش‌کن‌ها را مرتب تمیز کنید تا شعله یکنواخت بماند"),
    "جاروبرقی": ("خانه را بی‌دردسر تمیز نگه می‌دارد و گردوغبار فرش و پارکت را می‌گیرد",
                 "قدرت مکش و حجم مخزن را با متراژ خانه بسنجید",
                 "فیلتر را مرتب تکان دهید تا قدرت مکش کم نشود"),
    "لوازم آشپزخانه": ("کارهای روزانه آشپزخانه را ساده‌تر و سریع‌تر می‌کند",
                       "توان و ظرفیت را با نیاز روزانه و فضای کابینت هماهنگ کنید",
                       "پس از هر بار استفاده، بخش‌های جداشدنی را بشویید و خشک کنید"),
    "تلویزیون": ("تصویری شفاف برای فیلم، سریال و بازی فراهم می‌کند و با قابلیت‌های هوشمند به برنامه‌های آنلاین وصل می‌شود",
                 "اندازه را با فاصله مبل تا تلویزیون انتخاب کنید؛ برای فاصله ۲ تا ۳ متر، ۵۰ تا ۶۵ اینچ مناسب است",
                 "صفحه را فقط با دستمال میکروفایبر خشک تمیز کنید"),
    "کولر گازی": ("در تابستان خنک و در زمستان گرم نگه می‌دارد و با کمپرسور اینورتر مصرف برق را پایین می‌آورد",
                  "برای هر ۱۰ متر مربع حدود ۳۰۰۰ تا ۴۰۰۰ BTU در نظر بگیرید؛ در شهرهای گرم ظرفیت بیشتری لازم است",
                  "فیلترهای یونیت داخلی را هر ماه بشویید"),
}

REVIEWERS = ["مریم ر.", "علی ک.", "سارا م.", "حسین ج.", "نرگس ا.", "رضا ش.", "زهرا ن.", "محمد ت.",
             "فاطمه ب.", "امیر د.", "لیلا ص.", "مهدی ف.", "الهام ق.", "پویا ح.", "شیما ز.", "کاوه ی."]
REVIEW_TEXTS = {
    5: ["از خریدم خیلی راضی‌ام؛ کیفیت ساخت عالی است و بسته‌بندی سالم رسید.",
        "ارسال سریع بود و نصب هم بی‌دردسر انجام شد. پیشنهادش می‌کنم.",
        "با این قیمت انتظار این کیفیت را نداشتم. کاملاً ارزش خرید دارد.",
        "چند ماه است استفاده می‌کنم و هیچ مشکلی نداشته. صدایش هم خیلی کم است."],
    4: ["در کل راضی‌ام؛ فقط دفترچه راهنما می‌توانست کامل‌تر باشد.",
        "کارکردش خوب است. ارسال یک روز دیرتر از زمان اعلام‌شده رسید.",
        "کیفیت مناسب است، ولی کاش رنگ‌بندی بیشتری داشت."],
    3: ["برای استفاده معمولی بد نیست، ولی انتظار کمی بیشتر داشتم.",
        "قیمتش منصفانه است؛ کیفیت متوسط رو به خوب."],
}
QUESTIONS = [
    ("گارانتی این کالا چند ماه است و خدمات پس از فروش در شهرستان هم دارد؟",
     "{warranty}. خدمات پس از فروش در همه مراکز استان‌ها ارائه می‌شود."),
    ("هزینه ارسال به شهرستان چقدر است و چند روزه می‌رسد؟",
     "ارسال به شهرستان‌ها با باربری انجام می‌شود و معمولاً ۳ تا ۵ روز کاری طول می‌کشد. خریدهای بالای ۱۰ میلیون تومان ارسال رایگان دارند."),
    ("امکان خرید قسطی این کالا وجود دارد؟",
     "بله، این کالا با پیش‌پرداخت و اقساط ماهانه قابل خرید است؛ جزئیات در همین صفحه زیر قیمت آمده است."),
]

POSTS = [
    ("راهنمای خرید یخچال: چه ظرفیتی برای خانواده شما مناسب است؟", "guide", "fridge",
     "قبل از خرید یخچال این چند نکته را بدانید تا هم جا داشته باشید و هم برق کمتری مصرف کنید.",
     ["## ظرفیت مناسب", "برای یک یا دو نفر، یخچال‌های ۳۰۰ تا ۴۰۰ لیتری کافی است. خانواده‌های سه تا چهار نفره معمولاً با ۴۵۰ تا ۶۰۰ لیتر راحت‌ترند و برای خانواده‌های بزرگ‌تر، مدل‌های ساید بای ساید بالای ۶۰۰ لیتر پیشنهاد می‌شود.",
      "## کمپرسور اینورتر یا معمولی؟", "کمپرسور اینورتر سرعتش را با نیاز یخچال تنظیم می‌کند؛ بنابراین برق کمتری مصرف می‌کند، صدای کمتری دارد و عمر طولانی‌تری دارد. اختلاف قیمتش معمولاً در چند سال با صرفه‌جویی در قبض برق جبران می‌شود.",
      "## اندازه جای یخچال", "پیش از خرید عرض، عمق و ارتفاع محل را اندازه بگیرید و برای گردش هوا، دست‌کم ۵ تا ۱۰ سانتی‌متر فاصله از دیوار و کابینت در نظر بگیرید."]),
    ("مقایسه لباسشویی ۷، ۸ و ۹ کیلویی", "guide", "washer",
     "کدام ظرفیت لباسشویی به کار شما می‌آید؟ مقایسه‌ای ساده برای انتخاب درست.",
     ["## ظرفیت یعنی چه؟", "عدد کیلو، بیشترین وزن لباس خشکی است که در یک نوبت شسته می‌شود. ماشینی که همیشه نیمه‌پر کار کند هم آب و برق بیشتری هدر می‌دهد.",
      "## انتخاب بر اساس تعداد نفرات", "۷ کیلو برای یک تا دو نفر، ۸ کیلو برای سه نفر و ۹ کیلو به بالا برای چهار نفر و بیشتر مناسب است. اگر پتو و ملحفه را در خانه می‌شویید، ظرفیت بالاتر را انتخاب کنید.",
      "## دور موتور", "دور موتور بالاتر (۱۲۰۰ تا ۱۴۰۰) لباس را خشک‌تر بیرون می‌دهد و زمان خشک شدن را کوتاه می‌کند."]),
    ("۵ نکته برای کم کردن مصرف برق لوازم خانگی", "article", "ac",
     "با چند تغییر ساده در استفاده از لوازم خانگی، قبض برق را محسوس کمتر کنید.",
     ["## ۱. به برچسب انرژی دقت کنید", "رده‌های A++ و A+++ تا ۴۰ درصد کمتر از رده‌های پایین‌تر مصرف می‌کنند.",
      "## ۲. کولر را روی ۲۴ تا ۲۶ درجه تنظیم کنید", "هر درجه خنک‌تر، حدود ۶ درصد به مصرف برق کولر اضافه می‌کند.",
      "## ۳. یخچال را پر ولی نه شلوغ نگه دارید", "یخچال نیمه‌خالی سرما را زودتر از دست می‌دهد و یخچال بیش از حد پر، گردش هوا را مختل می‌کند.",
      "## ۴. لباسشویی و ظرفشویی را با ظرفیت کامل روشن کنید", "دو نوبت نیمه‌پر تقریباً دو برابر یک نوبت کامل آب و برق مصرف می‌کند.",
      "## ۵. دستگاه‌ها را در حالت آماده‌به‌کار رها نکنید", "تلویزیون و دستگاه‌های کوچک در حالت آماده‌به‌کار هم برق مصرف می‌کنند."]),
    ("راهنمای انتخاب اندازه تلویزیون بر اساس فاصله دید", "guide", "tv",
     "تلویزیون خیلی بزرگ یا خیلی کوچک تجربه تماشا را خراب می‌کند. اندازه مناسب را این‌طور پیدا کنید.",
     ["## قاعده ساده", "فاصله مبل تا تلویزیون را بر حسب سانتی‌متر بر ۲ (برای تلویزیون‌های 4K) تقسیم کنید تا اندازه مناسب بر حسب اینچ به دست آید؛ مثلاً برای فاصله ۲۵۰ سانتی‌متر، حدود ۵۵ اینچ.",
      "## 4K یا فول اچ‌دی؟", "در اندازه‌های ۵۰ اینچ به بالا، تفاوت 4K کاملاً دیده می‌شود. برای اتاق‌های کوچک و اندازه ۴۳ اینچ، فول اچ‌دی هم انتخاب خوبی است.",
      "## OLED، QLED یا LED؟", "OLED مشکی‌های عمیق و زاویه دید بهتری دارد، QLED روشن‌تر است و برای اتاق‌های پرنور مناسب‌تر، و LED اقتصادی‌ترین گزینه است."]),
    ("راهنمای خرید کولر گازی: چند BTU لازم دارید؟", "guide", "ac",
     "ظرفیت کم یعنی خنک نشدن خانه و ظرفیت زیاد یعنی هدر رفتن برق. ظرفیت درست را این‌طور حساب کنید.",
     ["## قاعده کلی", "برای مناطق معتدل، هر متر مربع حدود ۳۰۰ تا ۴۰۰ BTU لازم دارد؛ یعنی اتاق ۲۰ متری با کولر ۹۰۰۰ و پذیرایی ۳۵ متری با کولر ۱۲۰۰۰ تا ۱۸۰۰۰ خنک می‌شود.",
      "## شهرهای گرم و جنوبی", "در اهواز، بندرعباس و شهرهای مشابه، یک پله ظرفیت بالاتر انتخاب کنید. پنجره‌های رو به آفتاب و سقف‌های بلند هم نیاز را بیشتر می‌کنند.",
      "## اینورتر یا معمولی؟", "کولر اینورتر پس از رسیدن به دمای دلخواه خاموش و روشن نمی‌شود و فقط دورش را کم می‌کند؛ نتیجه، مصرف برق کمتر، صدای کمتر و دمای یکنواخت‌تر است.",
      "## نصب درست، نیمی از کار", "فاصله یونیت داخلی تا خارجی، شیب لوله آب و جای یونیت خارجی (سایه و دور از دیوار) روی بازده و عمر کولر اثر مستقیم دارد. نصب را به نصاب متخصص بسپارید."]),
    ("هفت اشتباه رایج در استفاده از یخچال", "article", "fridge",
     "این اشتباه‌های ساده هم برق بیشتری مصرف می‌کنند و هم عمر یخچال را کم می‌کنند.",
     ["## ۱. گذاشتن غذای داغ", "غذا را اول تا دمای اتاق خنک کنید؛ غذای داغ کمپرسور را مجبور به کار اضافه می‌کند.",
      "## ۲. چسباندن یخچال به دیوار", "دست‌کم ۱۰ سانتی‌متر فاصله بگذارید تا گرمای پشت یخچال خارج شود.",
      "## ۳. دمای نادرست", "دمای ۳ تا ۵ درجه برای یخچال و منفی ۱۸ درجه برای فریزر کافی است؛ سردتر فقط برق هدر می‌دهد.",
      "## ۴. باز گذاشتن طولانی در", "هر بار باز ماندن در، سرمای داخل را از بین می‌برد. قبل از باز کردن بدانید چه می‌خواهید.",
      "## ۵. تمیز نکردن نوار لاستیکی در", "نوار کثیف یا ترک‌خورده درز می‌دهد و سرما بیرون می‌رود.",
      "## ۶. پر کردن بیش از حد", "هوا باید بین مواد غذایی جریان داشته باشد تا همه قسمت‌ها یکنواخت سرد شوند.",
      "## ۷. بی‌توجهی به برفک", "در فریزرهای غیر نوفراست، برفک بیش از نیم سانتی‌متر را آب کنید."]),
    ("سرخ‌کن بدون روغن؛ ارزش خرید دارد؟", "article", "airfryer",
     "سرخ‌کن بدون روغن در خیلی از خانه‌ها جای ثابتی پیدا کرده. ببینیم واقعاً به کارتان می‌آید یا نه.",
     ["## چطور کار می‌کند؟", "هوای داغ با سرعت دور غذا می‌چرخد و سطح آن را برشته می‌کند؛ برای همین با یک قاشق روغن یا حتی بدون روغن، نتیجه‌ای شبیه سرخ کردن به دست می‌آید.",
      "## چه چیزهایی را می‌شود پخت؟", "سیب‌زمینی، مرغ، ماهی، سبزیجات، ناگت و حتی کیک کوچک. برای خورش و غذاهای آب‌دار مناسب نیست.",
      "## چه ظرفیتی بخرم؟", "۳ تا ۴ لیتر برای یک یا دو نفر و ۵ لیتر به بالا برای خانواده چهار نفره مناسب است.",
      "## جمع‌بندی", "اگر غذای سرخ‌کردنی زیاد می‌خورید و دنبال روشی سالم‌تر و تمیزتر هستید، خریدی است که پشیمانی ندارد."]),
    ("راهنمای خرید ماشین ظرفشویی", "guide", "dishwasher",
     "قبل از خرید ظرفشویی به ظرفیت، مصرف آب و برنامه‌های شستشو دقت کنید.",
     ["## تعداد سرویس", "یک سرویس یعنی ظرف‌های یک نفر برای یک وعده کامل. برای خانواده چهار نفره، ۱۲ تا ۱۴ سرویس مناسب است.",
      "## مصرف آب", "ظرفشویی‌های امروزی ۹ تا ۱۲ لیتر آب در هر نوبت مصرف می‌کنند؛ خیلی کمتر از شستشو با دست.",
      "## برنامه‌های کاربردی", "برنامه سریع برای ظرف‌های کم‌کثیف، برنامه اقتصادی برای صرفه‌جویی و برنامه شدید برای قابلمه‌ها، پرکاربردترین‌ها هستند.",
      "## جای نصب", "ظرفشویی به لوله آب، فاضلاب و پریز نزدیک نیاز دارد؛ پیش از خرید محل نصب را بررسی کنید."]),
    ("جاروبرقی سطلی یا کیسه‌ای؟", "guide", "vacuum",
     "هر دو نوع طرفداران خودشان را دارند. تفاوت‌ها را بدانید تا درست انتخاب کنید.",
     ["## جاروبرقی سطلی", "هزینه کیسه ندارد و مخزن شفافش نشان می‌دهد کی باید خالی شود. هنگام خالی کردن ممکن است کمی گرد پخش شود.",
      "## جاروبرقی کیسه‌ای", "گردوغبار داخل کیسه بسته می‌ماند؛ برای افراد حساس و مبتلا به آلرژی انتخاب بهتری است، ولی باید کیسه بخرید.",
      "## توان مکش", "برای فرش‌های پرز بلند، توان ۲۰۰۰ وات به بالا مناسب است. برای کف‌های سرامیک و پارکت، توان کمتر هم کافی است.",
      "## فیلتر HEPA", "اگر حساسیت دارید، مدلی با فیلتر HEPA انتخاب کنید تا ذرات ریز به هوا برنگردند."]),
    ("راهنمای خرید اجاق گاز", "guide", "stove",
     "تعداد شعله، جنس صفحه و ایمنی سه نکته اصلی در خرید اجاق گاز هستند.",
     ["## تعداد شعله", "برای آشپزی روزانه چهار شعله کافی است؛ اگر زیاد مهمان دارید یا چند غذا هم‌زمان می‌پزید، پنج شعله را انتخاب کنید.",
      "## شیشه یا استیل؟", "صفحه شیشه‌ای ظاهر شیک‌تری دارد و راحت‌تر تمیز می‌شود. صفحه استیل در برابر ضربه و حرارت مقاوم‌تر است.",
      "## ایمنی", "ترموکوپل (قطع خودکار گاز در صورت خاموش شدن شعله) را از ویژگی‌های ضروری بدانید، به‌خصوص اگر کودک در خانه دارید.",
      "## فندک", "فندک اتوماتیک کار با اجاق را راحت‌تر و ایمن‌تر می‌کند."]),
    ("نگهداری از ماشین لباسشویی؛ نکته‌هایی برای عمر بیشتر", "article", "washer",
     "با چند کار ساده، لباسشویی سال‌ها بی‌دردسر کار می‌کند و بوی بد نمی‌گیرد.",
     ["## در را باز بگذارید", "پس از هر شستشو در و کشوی پودر را چند ساعت باز بگذارید تا رطوبت خارج شود و بوی نم ایجاد نشود.",
      "## فیلتر پمپ را تمیز کنید", "هر یک تا دو ماه، فیلتر پایین دستگاه را باز و تمیز کنید؛ سکه و کش مو اغلب همان‌جا گیر می‌کنند.",
      "## از پودر مناسب استفاده کنید", "در لباسشویی‌های درب از جلو فقط از پودر مخصوص ماشین استفاده کنید؛ کف زیاد به دستگاه آسیب می‌زند.",
      "## برنامه تمیزکاری مخزن", "ماهی یک بار برنامه تمیزکاری مخزن یا شستشوی ۹۰ درجه را بدون لباس اجرا کنید."]),
    ("مایکروویو؛ استفاده درست و ایمن", "article", "microwave",
     "مایکروویو سریع‌ترین وسیله آشپزخانه است، به شرطی که درست از آن استفاده کنید.",
     ["## ظرف مناسب", "از ظرف‌های شیشه‌ای و سرامیکی مخصوص مایکروویو استفاده کنید. ظرف فلزی و فویل آلومینیومی جرقه ایجاد می‌کند.",
      "## گرم کردن یکنواخت", "غذا را در ظرف پهن کنید و وسط کار هم بزنید تا همه قسمت‌ها یکسان گرم شوند.",
      "## یخ‌زدایی", "برای یخ‌زدایی از برنامه مخصوص (Defrost) استفاده کنید و گوشت را بلافاصله بعد از آن بپزید.",
      "## تمیزکاری ساده", "یک کاسه آب و آبلیمو را ۳ دقیقه گرم کنید؛ بخار آن لکه‌ها را نرم می‌کند و با یک دستمال پاک می‌شوند."]),
    ("انتخاب اسپرسوساز خانگی", "guide", "coffee",
     "برای یک فنجان اسپرسوی خوب در خانه، به این ویژگی‌ها دقت کنید.",
     ["## فشار پمپ", "۱۵ بار فشار برای اسپرسوی خانگی کافی است و کرمای خوبی می‌دهد.",
      "## نازل بخار", "اگر کاپوچینو و لاته دوست دارید، مدلی با نازل بخار برای کف کردن شیر انتخاب کنید.",
      "## حجم مخزن", "مخزن ۱ تا ۱.۵ لیتری برای چند فنجان در روز کافی است.",
      "## قهوه آسیاب‌شده تازه", "مهم‌ترین عامل طعم، قهوه تازه است؛ دانه را کم‌کم بخرید و درست قبل از دم کردن آسیاب کنید."]),
]

PAGES = {
    "faq": ("سؤالات متداول", [
        "## ارسال سفارش چقدر طول می‌کشد؟",
        "سفارش‌های تهران معمولاً ۱ تا ۲ روز کاری و شهرستان‌ها ۳ تا ۵ روز کاری بعد از پرداخت تحویل داده می‌شوند.",
        "## هزینه ارسال چقدر است؟",
        "هزینه بر اساس روش ارسال در صفحه پرداخت نمایش داده می‌شود. خریدهای بالای ۱۰ میلیون تومان ارسال رایگان دارند.",
        "## آیا کالاها گارانتی دارند؟",
        "همه کالاها اصل و دارای گارانتی معتبر هستند؛ مدت گارانتی در صفحه هر کالا آمده است.",
        "## چطور سفارشم را پیگیری کنم؟",
        "از بخش «سفارش‌های من» در حساب کاربری، یا صفحه «پیگیری سفارش» با شماره سفارش و موبایل.",
        "## امکان خرید قسطی وجود دارد؟",
        "بله، برای کالاهایی که در صفحه‌شان طرح اقساط نمایش داده شده است."]),
    "return_policy": ("شرایط بازگشت کالا", [
        "## مهلت بازگشت",
        "تا ۷ روز پس از تحویل می‌توانید درخواست مرجوعی را از صفحه سفارش ثبت کنید.",
        "## شرایط کالای مرجوعی",
        "کالا باید سالم، بدون استفاده و در بسته‌بندی اصلی باشد. کالای معیوب یا مغایر با سفارش بدون هیچ هزینه‌ای مرجوع می‌شود.",
        "## بازگشت وجه",
        "پس از رسیدن و بررسی کالا، مبلغ به کیف پول شما برگشت داده می‌شود و می‌توانید در خرید بعدی از آن استفاده کنید."]),
    "terms": ("قوانین و مقررات", [
        "استفاده از این فروشگاه به معنای پذیرش قوانین زیر است.",
        "## ثبت سفارش",
        "قیمت‌ها به تومان و شامل مالیات بر ارزش افزوده است. سفارش پس از پرداخت موفق قطعی می‌شود.",
        "## موجودی",
        "در صورت اتمام ناگهانی موجودی پس از پرداخت، با شما تماس می‌گیریم و مبلغ کامل بازگردانده می‌شود.",
        "## حساب کاربری",
        "مسئولیت حفظ اطلاعات ورود به حساب با کاربر است."]),
    "privacy": ("حریم خصوصی", [
        "اطلاعات شما فقط برای پردازش سفارش، ارسال کالا و اطلاع‌رسانی درباره سفارش استفاده می‌شود.",
        "## اطلاعاتی که نگه می‌داریم",
        "نام، شماره موبایل، ایمیل و آدرس ارسال. اطلاعات کارت بانکی را ذخیره نمی‌کنیم؛ پرداخت در درگاه بانک انجام می‌شود.",
        "## پیامک‌های تبلیغاتی",
        "دریافت پیشنهادهای تخفیف را هر زمان می‌توانید از صفحه پروفایل خاموش کنید."]),
}


def _page_body(items) -> str:
    """Info pages take a paragraph's first line as its heading: join each «## heading» to the text after it."""
    paragraphs, heading = [], None
    for item in items:
        if item.startswith("## "):
            heading = item[3:]
        else:
            paragraphs.append(f"{heading}\n{item}" if heading else item)
            heading = None
    return "\n\n".join(paragraphs)


class Command(BaseCommand):
    help = "محتوای نمایشی کامل برای فروشگاه: کالا با عکس و توضیحات، نظرات، پرسش و پاسخ، بلاگ، صفحات و بنر"

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="حذف کاربران نمایشی و نظرات و پرسش‌هایشان")

    def handle(self, *args, clear=False, **options):
        from django.contrib.auth import get_user_model

        if clear:
            removed, _ = get_user_model().objects.filter(email__endswith=DEMO_DOMAIN).delete()
            self.stdout.write(self.style.SUCCESS(f"removed demo reviewers and their content ({removed} rows)"))
            return
        self.rng = random.Random(1405)
        call_command("seed_appliances", verbosity=0)
        with transaction.atomic():
            self._products()
            self._pictures_and_text()
            self._reviews_and_questions()
            self._blog()
            self._pages_and_settings()
            self._banners_shipping_coupon()
        call_command("seed_buying_guides", verbosity=0)
        from django.core.cache import cache

        cache.clear()
        self.stdout.write(self.style.SUCCESS("demo store ready"))

    # ------------------------------------------------------------ catalogue
    def _products(self):
        from apps.catalog.models import Attribute, Brand, Category, Product, ProductAttributeValue, ProductVariant

        for name, country in BRANDS:
            Brand.objects.get_or_create(name=name, defaults={"country": country, "slug": slugify(name, allow_unicode=True)})
        for cat_name, (_, specs) in CATEGORIES.items():
            cat, _ = Category.objects.get_or_create(name=cat_name, defaults={"slug": slugify(cat_name, allow_unicode=True)})
            for order, (spec, unit) in enumerate(specs):
                Attribute.objects.get_or_create(category=cat, name=spec, defaults={"unit": unit, "sort_order": order})

        now = timezone.now()
        for i, (brand, cat_name, name, price, sale, stock, shape, finish, specs, colours) in enumerate(PRODUCTS):
            category = Category.objects.get(name=cat_name)
            product, _ = Product.objects.update_or_create(
                slug=slugify(name, allow_unicode=True),
                defaults={
                    "name": name, "category": category, "brand": Brand.objects.get(name=brand),
                    "price": price, "sale_price": sale, "stock": stock, "is_active": True,
                    "warranty": f"{self.rng.choice([18, 24, 24, 36])} ماه گارانتی رسمی {brand}",
                    "energy_class": specs.get("رده انرژی", ""),
                    "country": dict(BRANDS).get(brand, ""),
                    "requires_install": cat_name in ("کولر گازی", "ماشین ظرفشویی") or "ساید" in name,
                    "installment_months": 12 if price >= 20 * M else 0,
                    "installment_down_payment": price // 4 if price >= 20 * M else 0,
                    "is_featured": i % 5 == 0,
                    # a few running deals end soon, so the home page has a flash sale
                    "sale_ends_at": now + timedelta(days=2, hours=i) if sale and i % 4 == 1 else None,
                },
            )
            for spec, value in specs.items():
                attribute = Attribute.objects.filter(category=category, name=spec).first()
                if attribute:
                    ProductAttributeValue.objects.update_or_create(
                        product=product, attribute=attribute, defaults={"value_text": value})
            for order, (colour, hex_code, _, colour_stock) in enumerate(colours):
                ProductVariant.objects.update_or_create(
                    product=product, color_name=colour,
                    defaults={"color_hex": hex_code, "price": price, "sale_price": sale,
                              "stock": colour_stock, "sort_order": order, "is_active": True},
                )
        # best sellers and «sold» counters for every product
        for product in Product.objects.filter(sold_count=0):
            Product.objects.filter(pk=product.pk).update(sold_count=self.rng.randint(3, 140))

    def _shape_for(self, product):
        for row in PRODUCTS:
            if slugify(row[2], allow_unicode=True) == product.slug:
                return row[6], row[7], row[9]
        shape = CATEGORIES.get(product.category.name, ("fridge", []))[0]
        if "سرخ" in product.name:
            shape = "airfryer"
        elif "قهوه" in product.name:
            shape = "coffee"
        elif "ساید" in product.name:
            shape = "side_by_side"
        return shape, self.rng.choice(["white", "silver", "steel"]), []

    def _pictures_and_text(self):
        from apps.catalog.models import Product, ProductImage

        for product in Product.objects.filter(is_active=True).select_related("category", "brand"):
            shape, finish, colours = self._shape_for(product)
            label = (product.brand.name if product.brand else "")
            label = "".join(ch for ch in label if ch.isascii())  # the drawing font has no Persian glyphs
            if not product.image:
                product.image.save(f"p{product.pk}.jpg", ContentFile(art.product_image(shape, finish, label, product.pk)), save=False)
            if not product.images.exists():
                shots = [(finish, product.pk + 1, 1.0), (finish, product.pk + 2, 1.6)]
                shots += [(c_finish, product.pk + 3 + n, 1.0) for n, (_, _, c_finish, _) in enumerate(colours)]
                for order, (shot_finish, backdrop, zoom) in enumerate(shots):
                    ProductImage.objects.create(
                        product=product, sort_order=order, alt=product.name,
                        image=ContentFile(art.product_image(shape, shot_finish, label, backdrop, zoom), name=f"p{product.pk}-{order}.jpg"),
                    )
            if len(product.description) < 200:
                product.description = self._description(product)
            product.save()

    def _description(self, product):
        use, tip, care = CATEGORY_COPY.get(product.category.name, CATEGORY_COPY["لوازم آشپزخانه"])
        specs = [f"{v.attribute.name}: {v.display()}" for v in product.attributes.select_related("attribute")]
        brand = product.brand.name if product.brand else "این برند"
        # shown as plain text (white-space: pre-line), so headings are lines ending in a colon
        features = [f"• {s}" for s in specs] or ["• طراحی ساده و کاربردی"]
        if product.energy_class:
            features.append(f"• رده انرژی {product.energy_class} برای مصرف برق کمتر")
        if product.warranty:
            features.append(f"• {product.warranty}")
        install = ("نصب این دستگاه توسط نصاب متخصص انجام می‌شود؛ هنگام خرید می‌توانید خدمات نصب را هم انتخاب کنید."
                   if product.requires_install else
                   "این کالا با بسته‌بندی اصلی کارخانه ارسال می‌شود و برای استفاده به نصب تخصصی نیاز ندارد.")
        return "\n\n".join([
            f"{product.name} انتخابی مطمئن از {brand} است که {use}.",
            "ویژگی‌های اصلی:\n" + "\n".join(features),
            f"برای چه کسانی مناسب است؟\n{tip}. اگر دنبال دستگاهی کم‌دردسر با کیفیت ساخت بالا هستید، "
            f"{product.name} گزینه‌ای است که سال‌ها همراهتان می‌ماند.",
            f"نکته نگهداری:\n{care}.",
            f"ارسال و نصب:\n{install}",
        ])

    # ------------------------------------------------------------ people
    def _reviewers(self):
        from django.contrib.auth import get_user_model

        users = []
        for n, name in enumerate(REVIEWERS):
            user, created = get_user_model().objects.get_or_create(
                email=f"customer{n + 1}{DEMO_DOMAIN}", defaults={"name": name, "accepts_marketing": False},
            )
            if created:
                user.set_unusable_password()
                user.save(update_fields=["password"])
            users.append(user)
        return users

    def _reviews_and_questions(self):
        from apps.catalog.models import Product
        from apps.reviews.models import ProductQuestion, Review

        users = self._reviewers()
        now = timezone.now()
        for product in Product.objects.filter(is_active=True):
            if not product.reviews.exists():
                for user in self.rng.sample(users, self.rng.randint(2, 6)):
                    rating = self.rng.choices([5, 4, 3], weights=[6, 3, 1])[0]
                    review = Review.objects.create(product=product, user=user, rating=rating, is_approved=True,
                                                   body=self.rng.choice(REVIEW_TEXTS[rating]))
                    Review.objects.filter(pk=review.pk).update(created_at=now - timedelta(days=self.rng.randint(3, 120)))
            if not product.questions.exists() and self.rng.random() < 0.7:
                for question, answer in self.rng.sample(QUESTIONS, self.rng.randint(1, 2)):
                    ProductQuestion.objects.create(
                        product=product, user=self.rng.choice(users), body=question, is_published=True,
                        answer=answer.format(warranty=product.warranty or "۱۸ ماه گارانتی رسمی"),
                        answered_at=now - timedelta(days=self.rng.randint(1, 60)),
                    )

    # ------------------------------------------------------------ content
    def _blog(self):
        from apps.blog.models import Post

        palette = [((24, 96, 120), (12, 58, 76)), ((70, 60, 140), (36, 30, 90)), ((30, 120, 90), (14, 70, 52)), ((140, 70, 40), (90, 40, 20))]
        now = timezone.now()
        for i, (title, kind, shape, excerpt, body) in enumerate(POSTS):
            post, created = Post.objects.get_or_create(
                slug=slugify(title, allow_unicode=True)[:200],
                defaults={"title": title, "kind": kind, "excerpt": excerpt, "body": "\n\n".join(body),
                          "is_published": True, "published_at": now - timedelta(days=7 * (i + 1))},
            )
            if not post.cover:
                post.cover.save(f"post{post.pk}.jpg", ContentFile(art.cover_image(shape, *palette[i % len(palette)])))

    def _pages_and_settings(self):
        from apps.common.models import SiteSettings, StaticPage

        for key, (title, items) in PAGES.items():
            body = _page_body(items)
            page, _ = StaticPage.objects.get_or_create(key=key, defaults={"title": title, "body": body})
            if len(page.body) < 150:
                page.title, page.body = title, body
                page.save()
        s = SiteSettings.load()
        if not s.about_text:
            s.about_text = (
                "ما فروشگاهی تخصصی برای لوازم خانگی هستیم. همه کالاها اصل، با گارانتی معتبر و قیمت منصفانه عرضه می‌شوند.\n\n"
                "پیش از خرید، راهنمای انتخاب و مقایسه کالاها کمکتان می‌کند انتخاب درستی داشته باشید و بعد از خرید، "
                "تیم پشتیبانی تا نصب و راه‌اندازی همراهتان است."
            )
        if s.free_shipping_threshold is None:
            s.free_shipping_threshold = 10 * M
        if not s.install_fee:
            s.install_fee = 450_000
        s.save()

    def _banners_shipping_coupon(self):
        from apps.catalog.models import Banner, Category
        from apps.discounts.models import Coupon
        from apps.orders.models import ShippingMethod

        if not Banner.objects.exists():
            banners = [
                ("جشنواره لوازم خانگی", "تا ۲۰٪ تخفیف یخچال، لباسشویی و تلویزیون", ((20, 96, 116), (8, 52, 68)), ["fridge", "washer", "tv"], "/products/?sale=1"),
                ("تابستان خنک با کولرهای اینورتر", "مصرف برق کمتر، آسایش بیشتر — با نصب تخصصی", ((40, 90, 150), (18, 44, 90)), ["ac", "ac"], "کولر گازی"),
                ("آشپزخانه‌ای هوشمندتر", "سرخ‌کن بدون روغن، مایکروویو و اسپرسوساز", ((120, 70, 40), (70, 36, 18)), ["airfryer", "microwave", "coffee"], "لوازم آشپزخانه"),
            ]
            for order, (title, subtitle, colours, shapes, link) in enumerate(banners):
                if not link.startswith("/"):
                    link = Category.objects.get(name=link).get_absolute_url()
                banner = Banner(title=title, subtitle=subtitle, link=link, sort_order=order)
                banner.image.save(f"banner{order + 1}.jpg", ContentFile(art.banner_image(*colours, shapes)), save=False)
                banner.save()
        for order, (name, description, price) in enumerate([
            ("پست پیشتاز", "کالاهای کوچک — ۲ تا ۴ روز کاری", 150_000),
            ("پیک تهران", "تحویل در تهران — ۱ روز کاری", 90_000),
            ("باربری کالای سنگین", "یخچال، لباسشویی و کولر — ۳ تا ۵ روز کاری", 450_000),
        ]):
            ShippingMethod.objects.get_or_create(name=name, defaults={"description": description, "price": price, "sort_order": order})
        now = timezone.now()
        Coupon.objects.get_or_create(code="WELCOME10", defaults={
            "kind": Coupon.Kind.PERCENT, "value": 10, "max_discount_amount": 1_500_000, "first_order_only": True,
            "valid_from": now, "valid_to": now + timedelta(days=365),
        })
