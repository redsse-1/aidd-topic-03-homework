from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from dashboard.models import Share
from dashboard.services.market_data import get_provider
from dashboard.services.price_history import backfill_history


class Command(BaseCommand):
    help = "Fill price history from daily candles"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=settings.HISTORY_BACKFILL_DAYS)
        parser.add_argument("--ticker", action="append", help="Only these tickers")

    def handle(self, *args, **options):
        shares = Share.objects.order_by("ticker")
        if options["ticker"]:
            shares = shares.filter(ticker__in=options["ticker"])
        if not shares.exists():
            raise CommandError("Акции не найдены: сначала выполните add_shares")

        saved, failed = backfill_history(
            get_provider(),
            shares,
            lambda share: options["days"],
            settings.HISTORY_REQUEST_PAUSE,
        )
        self.stdout.write(f"Записей истории: {saved}, акций с ошибкой: {failed}")
        if failed == shares.count():
            raise CommandError("История не загружена ни по одной акции")
