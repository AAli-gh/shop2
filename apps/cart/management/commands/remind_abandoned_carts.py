from django.core.management.base import BaseCommand

from apps.cart.reminders import carts_to_remind, remind_abandoned_carts


class Command(BaseCommand):
    help = "پیامک یادآوری سبد خرید رهاشده به مشتریان دارای موبایل تأییدشده (اجرای زمان‌بندی‌شده ساعتی)"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="فقط تعداد، بدون ارسال پیامک")

    def handle(self, *args, dry_run, **options):
        if dry_run:
            self.stdout.write(f"would remind {carts_to_remind().count()} cart(s)")
            return
        self.stdout.write(f"reminded {remind_abandoned_carts()} cart(s)")
