"""Starter buying guides for each appliance category, built on the specs the shop already has.

    python manage.py seed_buying_guides

Only questions whose spec exists in that category are added, and a category that already has a
guide is left alone, so it is safe to re-run. Edit the questions and ranges afterwards in the admin.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Attribute, Category
from apps.guides.models import BuyingGuide, GuideAnswer, GuideQuestion

M = 1_000_000

# category name -> (title, intro, [(question, hint, spec name or None for price, [(label, rule, required, reason)])])
GUIDES = {
    "یخچال و فریزر": (
        "کدام یخچال برای شما مناسب است؟",
        "با سه سؤال کوتاه، یخچالی را پیدا کنید که به اندازه خانواده و بودجه‌تان باشد.",
        [
            ("چند نفر در خانه زندگی می‌کنید؟", "", "ظرفیت", [
                ("۱ تا ۲ نفر", {"max_value": 400}, False, "جمع‌وجور، مناسب ۱ تا ۲ نفر"),
                ("۳ تا ۴ نفر", {"min_value": 400, "max_value": 600}, False, "مناسب خانواده ۳ تا ۴ نفره"),
                ("۵ نفر یا بیشتر", {"min_value": 600}, False, "جادار، مناسب خانواده پرجمعیت"),
            ]),
            ("مصرف برق چقدر برایتان مهم است؟", "کمپرسور اینورتر برق کمتری مصرف می‌کند و بی‌صداتر است.", "کمپرسور", [
                ("خیلی مهم است", {"text_contains": "اینورتر"}, False, "کمپرسور اینورتر، کم‌مصرف و کم‌صدا"),
                ("فرقی نمی‌کند", {}, False, ""),
            ]),
            ("بودجه شما چقدر است؟", "", None, [
                ("تا ۲۰ میلیون تومان", {"price_max": 20 * M}, True, ""),
                ("۲۰ تا ۴۰ میلیون تومان", {"price_min": 20 * M, "price_max": 40 * M}, True, ""),
                ("بیشتر از ۴۰ میلیون تومان", {"price_min": 40 * M}, False, ""),
            ]),
        ],
    ),
    "ماشین لباسشویی": (
        "کدام لباسشویی برای شما مناسب است؟",
        "ظرفیت، سرعت خشک‌کردن و بودجه را بگویید تا لباسشویی مناسب را پیشنهاد کنیم.",
        [
            ("چند نفر در خانه زندگی می‌کنید؟", "", "ظرفیت", [
                ("۱ تا ۲ نفر", {"max_value": 7}, False, "مناسب ۱ تا ۲ نفر"),
                ("۳ تا ۴ نفر", {"min_value": 7, "max_value": 9}, False, "مناسب خانواده ۳ تا ۴ نفره"),
                ("۵ نفر یا بیشتر", {"min_value": 9}, False, "ظرفیت بالا برای خانواده پرجمعیت"),
            ]),
            ("لباس‌ها خشک‌تر بیرون بیایند؟", "دور موتور بالاتر یعنی آب بیشتری از لباس گرفته می‌شود.", "دور موتور", [
                ("بله، مهم است", {"min_value": 1400}, False, "دور موتور بالا، لباس خشک‌تر"),
                ("فرقی نمی‌کند", {}, False, ""),
            ]),
            ("بودجه شما چقدر است؟", "", None, [
                ("تا ۲۰ میلیون تومان", {"price_max": 20 * M}, True, ""),
                ("بیشتر از ۲۰ میلیون تومان", {"price_min": 20 * M}, False, ""),
            ]),
        ],
    ),
    "ماشین ظرفشویی": (
        "کدام ظرفشویی برای شما مناسب است؟",
        "اندازه خانواده، مصرف آب و بودجه را بگویید تا ظرفشویی مناسب را پیدا کنیم.",
        [
            ("معمولاً برای چند نفر ظرف می‌شویید؟", "", "تعداد سرویس", [
                ("تا ۴ نفر", {"max_value": 12}, False, "مناسب خانواده کوچک"),
                ("بیشتر از ۴ نفر یا مهمانی زیاد", {"min_value": 13}, False, "ظرفیت بالا برای مهمانی‌ها"),
            ]),
            ("مصرف آب کم برایتان مهم است؟", "مدل‌های کم‌مصرف کمتر از ۱۰ لیتر در هر نوبت آب می‌خواهند.", "مصرف آب", [
                ("بله، مهم است", {"max_value": 10}, False, "کم‌مصرف در آب"),
                ("فرقی نمی‌کند", {}, False, ""),
            ]),
            ("بودجه شما چقدر است؟", "", None, [
                ("تا ۲۵ میلیون تومان", {"price_max": 25 * M}, True, ""),
                ("بیشتر از ۲۵ میلیون تومان", {"price_min": 25 * M}, False, ""),
            ]),
        ],
    ),
    "گاز و اجاق": (
        "کدام اجاق گاز برای آشپزخانه شما مناسب است؟",
        "تعداد شعله، جنس صفحه و بودجه را انتخاب کنید.",
        [
            ("چقدر آشپزی می‌کنید؟", "", "تعداد شعله", [
                ("روزانه و ساده", {"max_value": 4}, False, "چهار شعله، کافی برای آشپزی روزانه"),
                ("زیاد و چندغذایی", {"min_value": 5}, False, "پنج شعله برای پخت هم‌زمان چند غذا"),
            ]),
            ("کدام صفحه را ترجیح می‌دهید؟", "شیشه شیک‌تر است و استیل در برابر ضربه مقاوم‌تر.", "جنس صفحه", [
                ("شیشه‌ای", {"text_contains": "شیشه"}, False, "صفحه شیشه‌ای، تمیزکاری آسان"),
                ("استیل", {"text_contains": "استیل"}, False, "صفحه استیل مقاوم"),
                ("فرقی نمی‌کند", {}, False, ""),
            ]),
            ("بودجه شما چقدر است؟", "", None, [
                ("تا ۱۰ میلیون تومان", {"price_max": 10 * M}, True, ""),
                ("بیشتر از ۱۰ میلیون تومان", {"price_min": 10 * M}, False, ""),
            ]),
        ],
    ),
    "جاروبرقی": (
        "کدام جاروبرقی برای خانه شما مناسب است؟",
        "نوع کف خانه، مخزن و بودجه را بگویید.",
        [
            ("کف خانه بیشتر چیست؟", "برای فرش‌های پرز بلند، توان بالاتر لازم است.", "توان", [
                ("فرش زیاد", {"min_value": 2200}, False, "مکش قوی برای فرش"),
                ("بیشتر سرامیک و پارکت", {"max_value": 2200}, False, "توان مناسب کف‌های صاف"),
            ]),
            ("کیسه یا سطل؟", "مدل سطلی هزینه کیسه ندارد؛ مدل کیسه‌ای گرد کمتری پخش می‌کند.", "نوع", [
                ("بدون کیسه (سطلی)", {"text_contains": "سطلی"}, False, "بدون نیاز به خرید کیسه"),
                ("کیسه‌ای", {"text_contains": "کیسه"}, False, "مناسب افراد حساس به گردوغبار"),
                ("فرقی نمی‌کند", {}, False, ""),
            ]),
            ("بودجه شما چقدر است؟", "", None, [
                ("تا ۱۰ میلیون تومان", {"price_max": 10 * M}, True, ""),
                ("بیشتر از ۱۰ میلیون تومان", {"price_min": 10 * M}, False, ""),
            ]),
        ],
    ),
    "لوازم آشپزخانه": (
        "کدام وسیله آشپزخانه به کارتان می‌آید؟",
        "بگویید بیشتر چه چیزی می‌خواهید تا گزینه مناسب را پیشنهاد کنیم.",
        [
            ("بیشتر به چه کاری نیاز دارید؟", "", "نوع", [
                ("سرخ کردن کم‌روغن", {"text_contains": "سرخ"}, False, "پخت سالم‌تر با روغن کمتر"),
                ("گرم کردن سریع غذا", {"text_contains": "مایکروویو"}, False, "گرم کردن و یخ‌زدایی سریع"),
                ("قهوه و اسپرسو", {"text_contains": "قهوه"}, False, "قهوه تازه در خانه"),
                ("اسپرسوی حرفه‌ای", {"text_contains": "اسپرسو"}, False, "اسپرسو با فشار بالا"),
            ]),
            ("بودجه شما چقدر است؟", "", None, [
                ("تا ۸ میلیون تومان", {"price_max": 8 * M}, True, ""),
                ("بیشتر از ۸ میلیون تومان", {"price_min": 8 * M}, False, ""),
            ]),
        ],
    ),
    "تلویزیون": (
        "کدام تلویزیون برای شما مناسب است؟",
        "فاصله مبل تا تلویزیون، کیفیت تصویر و بودجه را بگویید.",
        [
            ("فاصله مبل تا تلویزیون چقدر است؟", "اندازه مناسب به فاصله دید بستگی دارد.", "اندازه صفحه", [
                ("کمتر از ۲ متر", {"max_value": 45}, False, "اندازه مناسب اتاق‌های کوچک"),
                ("۲ تا ۳ متر", {"min_value": 46, "max_value": 55}, False, "اندازه مناسب پذیرایی معمولی"),
                ("بیشتر از ۳ متر", {"min_value": 56}, False, "صفحه بزرگ برای پذیرایی جادار"),
            ]),
            ("کیفیت تصویر چقدر مهم است؟", "", "نوع پنل", [
                ("بهترین تصویر (OLED)", {"text_contains": "OLED"}, False, "پنل OLED با مشکی عمیق"),
                ("روشن و رنگی (QLED)", {"text_contains": "QLED"}, False, "پنل QLED روشن"),
                ("فرقی نمی‌کند", {}, False, ""),
            ]),
            ("بودجه شما چقدر است؟", "", None, [
                ("تا ۳۰ میلیون تومان", {"price_max": 30 * M}, True, ""),
                ("۳۰ تا ۶۰ میلیون تومان", {"price_min": 30 * M, "price_max": 60 * M}, True, ""),
                ("بیشتر از ۶۰ میلیون تومان", {"price_min": 60 * M}, False, ""),
            ]),
        ],
    ),
    "کولر گازی": (
        "کدام کولر گازی برای خانه شما مناسب است؟",
        "متراژ فضا، مصرف برق و بودجه را بگویید تا ظرفیت درست را پیشنهاد کنیم.",
        [
            ("متراژ فضایی که باید خنک شود چقدر است؟", "در شهرهای گرم و جنوبی، یک پله ظرفیت بالاتر انتخاب کنید.", "ظرفیت", [
                ("تا ۲۵ متر", {"max_value": 9000}, False, "ظرفیت مناسب اتاق خواب"),
                ("۲۵ تا ۴۰ متر", {"min_value": 12000, "max_value": 12000}, False, "ظرفیت مناسب پذیرایی کوچک"),
                ("۴۰ تا ۶۰ متر", {"min_value": 18000, "max_value": 18000}, False, "ظرفیت مناسب پذیرایی متوسط"),
                ("بیشتر از ۶۰ متر", {"min_value": 24000}, False, "ظرفیت بالا برای فضای بزرگ"),
            ]),
            ("مصرف برق کم برایتان مهم است؟", "کمپرسور اینورتر تا ۴۰٪ کمتر برق مصرف می‌کند.", "کمپرسور", [
                ("بله، خیلی", {"text_contains": "اینورتر"}, False, "کمپرسور اینورتر کم‌مصرف"),
                ("فرقی نمی‌کند", {}, False, ""),
            ]),
            ("بودجه شما چقدر است؟", "", None, [
                ("تا ۳۵ میلیون تومان", {"price_max": 35 * M}, True, ""),
                ("بیشتر از ۳۵ میلیون تومان", {"price_min": 35 * M}, False, ""),
            ]),
        ],
    ),
}


class Command(BaseCommand):
    help = "راهنمای انتخاب نمونه برای هر دسته لوازم خانگی، بر اساس مشخصات فنی موجود"

    @transaction.atomic
    def handle(self, *args, **options):
        made = 0
        for category_name, (title, intro, questions) in GUIDES.items():
            category = Category.objects.filter(name=category_name).first()
            if category is None or BuyingGuide.objects.filter(category=category).exists():
                continue
            guide = BuyingGuide.objects.create(category=category, title=title, intro=intro)
            for q_order, (text, hint, spec_name, options) in enumerate(questions):
                attribute = None
                if spec_name:
                    attribute = Attribute.objects.filter(category=category, name=spec_name).first()
                    if attribute is None:
                        continue  # this shop doesn't record that spec
                question = GuideQuestion.objects.create(guide=guide, text=text, hint=hint, sort_order=q_order)
                for a_order, (label, rule, required, reason) in enumerate(options):
                    spec_rule = {k: v for k, v in rule.items() if k in ("min_value", "max_value", "text_contains")}
                    GuideAnswer.objects.create(
                        question=question, label=label, sort_order=a_order, reason=reason, is_required=required,
                        attribute=attribute if spec_rule else None,
                        **rule,
                    )
            made += 1
        self.stdout.write(self.style.SUCCESS(f"{made} buying guide(s) created"))
