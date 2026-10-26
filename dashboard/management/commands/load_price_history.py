from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from zoneinfo import ZoneInfo

from dashboard.models import Share
from dashboard.services.market_data import get_market_data_provider
from dashboard.services.price_history import upsert_share_prices

MOSCOW = ZoneInfo("Europe/Moscow")


class Command(BaseCommand):
    help = "Load historical daily closing prices from the configured provider"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=365,
            help="Number of calendar days to load (default: 365)",
        )
        parser.add_argument(
            "--ticker",
            help="Load history only for this ticker",
        )

    def handle(self, *args, **options):
        days = options["days"]
        if days < 1:
            raise CommandError("--days must be greater than zero.")

        shares = Share.objects.all().order_by("ticker")
        if options["ticker"]:
            shares = shares.filter(ticker=options["ticker"].upper())

        provider = get_market_data_provider()
        today = timezone.localdate(timezone.now(), timezone=MOSCOW)
        start_date = today - timedelta(days=days - 1)
        share_count = shares.count()
        total = 0
        for share in shares.iterator():
            candles = provider.get_history(share, days=days)
            total += upsert_share_prices(
                share,
                (
                    (point.time, point.close)
                    for point in candles
                    if start_date <= point.time <= today
                ),
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded or updated {total} daily prices for {share_count} shares."
            )
        )
