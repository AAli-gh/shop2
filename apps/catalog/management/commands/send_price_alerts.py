from django.core.management.base import BaseCommand

from apps.catalog.price_alerts import send_price_alerts


class Command(BaseCommand):
    help = "اطلاع کاهش قیمت به مشتریانی که قیمت محصولی را دنبال می‌کنند (اجرای زمان‌بندی‌شده ساعتی)"

    def handle(self, *args, **options):
        self.stdout.write(f"sent {send_price_alerts()} price alert(s)")
