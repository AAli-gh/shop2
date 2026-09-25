from django.core.management.base import BaseCommand

from apps.orders.review_requests import orders_to_ask, request_reviews


class Command(BaseCommand):
    help = "درخواست ثبت نظر از مشتریانی که سفارششان چند روز پیش تحویل شده (اجرای زمان‌بندی‌شده ساعتی)"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="فقط تعداد، بدون ارسال")

    def handle(self, *args, dry_run, **options):
        if dry_run:
            self.stdout.write(f"would ask {orders_to_ask().count()} customer(s)")
            return
        self.stdout.write(f"asked {request_reviews()} customer(s) for a review")
