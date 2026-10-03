from django.core.management.base import BaseCommand

from apps.crm.winback import candidates, send_winback


class Command(BaseCommand):
    help = "کد تخفیف شخصی برای مشتریانی که مدتی خرید نکرده‌اند (اجرای زمان‌بندی‌شده؛ فقط وقتی کمپین در تنظیمات روشن است)"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="فقط تعداد، بدون ارسال")

    def handle(self, *args, dry_run, **options):
        if dry_run:
            self.stdout.write(f"{candidates().count()} customer(s) are due a win-back offer")
            return
        self.stdout.write(f"sent {send_winback()} win-back offer(s)")
