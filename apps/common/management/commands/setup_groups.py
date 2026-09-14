from django.core.management.base import BaseCommand

from apps.common.groups import setup_groups


class Command(BaseCommand):
    help = "Create/refresh staff role groups (پشتیبانی، مالی، انبار)."

    def handle(self, *args, **options):
        created = setup_groups()
        if created:
            self.stdout.write(self.style.SUCCESS(f"Groups created: {', '.join(created)}"))
        else:
            self.stdout.write("Groups already exist (permissions refreshed).")
