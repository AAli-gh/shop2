from django.core.management.base import BaseCommand

from apps.orders.services import expire_unpaid_orders


class Command(BaseCommand):
    help = "لغو سفارش‌های پرداخت‌نشده پس از مهلت پرداخت و آزادسازی موجودی/کوپن (اجرای زمان‌بندی‌شده هر ۱۰ دقیقه)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--minutes", type=int, default=None,
            help="مهلت پرداخت به دقیقه (پیش‌فرض: ORDER_PAYMENT_TIMEOUT_MINUTES)",
        )
        parser.add_argument("--dry-run", action="store_true", help="فقط فهرست، بدون لغو")

    def handle(self, *args, minutes, dry_run, **options):
        numbers = expire_unpaid_orders(older_than_minutes=minutes, dry_run=dry_run)
        verb = "would expire" if dry_run else "expired"
        suffix = f": {', '.join(numbers)}" if numbers else ""
        self.stdout.write(f"{verb} {len(numbers)} order(s){suffix}")
