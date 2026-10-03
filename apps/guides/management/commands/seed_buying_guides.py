"""Starter buying guides for fridges and washing machines, built on the specs the shop already has.

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
}


class Command(BaseCommand):
    help = "راهنمای انتخاب نمونه برای یخچال و لباسشویی، بر اساس مشخصات فنی موجود"

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
