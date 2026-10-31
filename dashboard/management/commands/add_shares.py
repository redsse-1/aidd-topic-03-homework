from django.core.management.base import BaseCommand, CommandError

from dashboard.services.market_data import MarketDataError, get_provider
from dashboard.services.shares import sync_shares


class Command(BaseCommand):
    help = "Add shares to DB"

    def handle(self, *args, **options):
        try:
            saved = sync_shares(get_provider())
        except MarketDataError as e:
            raise CommandError(str(e)) from e
        self.stdout.write(f"Акций сохранено: {saved}")
