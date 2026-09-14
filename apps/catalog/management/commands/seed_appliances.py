"""Seed a realistic home-appliance catalog (brands, categories, specs, products).

Idempotent: uses get_or_create, safe to re-run.
    python manage.py seed_appliances
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from apps.catalog.models import (
    Attribute, Brand, Category, Product, ProductAttributeValue,
)


CATS = [
    ("یخچال و فریزر", [
        ("ظرفیت", "لیتر"), ("تعداد درب", ""), ("رده انرژی", ""),
        ("کمپرسور", ""), ("فریزر", ""),
    ]),
    ("ماشین لباسشویی", [
        ("ظرفیت", "کیلوگرم"), ("دور موتور", "دور/دقیقه"), ("تعداد برنامه", ""),
        ("رنگ", ""),
    ]),
    ("ماشین ظرفشویی", [
        ("تعداد سرویس", ""), ("برنامه شستشو", ""), ("مصرف آب", "لیتر"),
    ]),
    ("گاز و اجاق", [
        ("تعداد شعله", ""), ("جنس صفحه", ""), ("ولوم", ""),
    ]),
    ("جاروبرقی", [
        ("توان", "وات"), ("مخزن", "لیتر"), ("نوع", ""),
    ]),
    ("لوازم آشپزخانه", [
        ("توان", "وات"), ("ظرفیت", "لیتر"), ("نوع", ""),
    ]),
]

BRANDS = [
    ("پارس", "ایران"), ("استرلین", "ایران"), ("دوو", "کره جنوبی"),
    ("اسنوا", "ایران"), ("جی‌پلاس", "ایران"), ("بوش", "آلمان"),
    ("ال‌جی", "کره جنوبی"), ("سامسونگ", "کره جنوبی"),
]

# brand_name -> list of (cat_name, product name, price, sale_price, stock, warranty, energy, country, weight, install, months, down, {attr: value})
PRODUCTS = [
    ("پارس", "یخچال و فریزر", "یخچال فریزر پارس مدل ۲۴ فوت", 22_500_000, 20_900_000, 5,
     "۲۴ ماه گارانتی پارس", "A+", "ایران", 95, False, 12, 5_000_000,
     {"ظرفیت": "650", "تعداد درب": "دو درب", "رده انرژی": "A+", "کمپرسور": "خطی", "فریزر": "بالا"}),
    ("استرلین", "یخچال و فریزر", "یخچال استرلین مدل ساید بای ساید", 48_000_000, 45_000_000, 3,
     "۱۸ ماه گارانتی استرلین", "A++", "ایران", 140, True, 12, 12_000_000,
     {"ظرفیت": "620", "تعداد درب": "چهار درب", "رده انرژی": "A++", "کمپرسور": "اینورتر", "فریزر": "ساید"}),
    ("دوو", "ماشین لباسشویی", "ماشین لباسشویی دوو ۸ کیلویی", 18_900_000, 17_500_000, 8,
     "۲۰ ماه گارانتی دوو", "A+++", "کره جنوبی", 62, False, 6, 4_000_000,
     {"ظرفیت": "8", "دور موتور": "1200", "تعداد برنامه": "15", "رنگ": "سفید"}),
    ("اسنوا", "ماشین لباسشویی", "لباسشویی اسنوا ۹ کیلویی اینورتر", 24_500_000, 22_900_000, 4,
     "۲۴ ماه گارانتی اسنوا", "A+++", "ایران", 68, False, 12, 6_000_000,
     {"ظرفیت": "9", "دور موتور": "1400", "تعداد برنامه": "16", "رنگ": "نقره‌ای"}),
    ("بوش", "ماشین ظرفشویی", "ظرفشویی بوش ۱۴ نفره", 32_000_000, None, 2,
     "۲۴ ماه گارانتی بوش", "A++", "ترکیه", 55, True, 0, 0,
     {"تعداد سرویس": "14", "برنامه شستشو": "6", "مصرف آب": "9.5"}),
    ("جی‌پلاس", "گاز و اجاق", "گاز رومیزی جی‌پلاس سه شعله", 4_800_000, 4_200_000, 12,
     "۱۲ ماه گارانتی", "", "ایران", 8, False, 0, 0,
     {"تعداد شعله": "3", "جنس صفحه": "شیشه", "ولوم": "معمولی"}),
    ("ال‌جی", "جاروبرقی", "جاروبرقی ال‌جی ۲۰۰۰ وات", 9_500_000, 8_900_000, 6,
     "۱۸ ماه گارانتی", "A", "کره جنوبی", 5, False, 0, 0,
     {"توان": "2000", "مخزن": "2.5", "نوع": "کیسه‌ای"}),
    ("سامسونگ", "لوازم آشپزخانه", "سرخ‌کن بدون روغن سامسونگ ۸ لیتری", 15_200_000, 13_900_000, 7,
     "۱۸ ماه گارانتی سامسونگ", "A", "کره جنوبی", 4, False, 6, 3_000_000,
     {"توان": "1500", "ظرفیت": "8", "نوع": "سرخ‌کن بدون روغن"}),
    ("پارس", "لوازم آشپزخانه", "نیمکت قهوه‌ساز پارس", 2_800_000, None, 20,
     "۱۲ ماه گارانتی", "", "ایران", 2, False, 0, 0,
     {"توان": "800", "ظرفیت": "1.5", "نوع": "قهوه‌ساز"}),
    ("اسنوا", "یخچال و فریزر", "فریزر اسنوا ۵ کشو", 16_000_000, 14_500_000, 3,
     "۲۴ ماه گارانتی اسنوا", "A+", "ایران", 58, False, 6, 4_000_000,
     {"ظرفیت": "340", "تعداد درب": "تک درب", "رده انرژی": "A+", "کمپرسور": "معمولی", "فریزر": "کشو"}),
]


class Command(BaseCommand):
    help = "Seed home-appliance brands, categories, attributes and products."

    def handle(self, *args, **options):
        # clean demo products of the generic type first? no — keep both, just add appliances
        brands = {}
        for name, country in BRANDS:
            b, _ = Brand.objects.get_or_create(
                name=name, defaults={"country": country, "slug": slugify(name, allow_unicode=True)}
            )
            brands[name] = b

        attrs = {}  # (cat_name, attr_name) -> Attribute
        for cat_name, cat_attrs in CATS:
            cat, _ = Category.objects.get_or_create(
                name=cat_name, defaults={"slug": slugify(cat_name, allow_unicode=True)}
            )
            for order, (aname, unit) in enumerate(cat_attrs):
                a, _ = Attribute.objects.get_or_create(
                    category=cat, name=aname,
                    defaults={"unit": unit, "sort_order": order, "data_type": Attribute.DataType.TEXT},
                )
                attrs[(cat_name, aname)] = a

        created = 0
        for brand_name, cat_name, pname, price, sale_price, stock, warranty, energy, country, weight, install, months, down, spec_map in PRODUCTS:
            slug = slugify(pname, allow_unicode=True)
            product, was_new = Product.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": pname, "category": Category.objects.get(name=cat_name),
                    "brand": brands[brand_name],
                    "price": price, "sale_price": sale_price, "stock": stock,
                    "warranty": warranty, "energy_class": energy, "country": country,
                    "weight_kg": Decimal(str(weight)), "requires_install": install,
                    "installment_months": months, "installment_down_payment": down,
                    "is_active": True, "description": f"{pname} — {brand_name}. ارسال سریع با گارانتی معتبر.",
                },
            )
            for aname, value in spec_map.items():
                a = attrs.get((cat_name, aname))
                if a:
                    ProductAttributeValue.objects.update_or_create(
                        product=product, attribute=a, defaults={"value_text": str(value)}
                    )
            if was_new:
                created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Appliances seeded: {len(brands)} brands, {len(attrs)} attributes, {created} new products."
        ))
