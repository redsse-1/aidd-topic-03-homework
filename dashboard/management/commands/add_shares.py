from decimal import Decimal

from django.core.management.base import BaseCommand

from dashboard.models import Share
from dashboard.services.market_data import get_market_data_provider


class Command(BaseCommand):
    help = "Import available shares from the configured market-data provider"

    def handle(self, *args, **options):
        provider = get_market_data_provider()
        instruments = provider.list_instruments()
        if not instruments:
            self.stdout.write(self.style.WARNING("The provider returned no shares."))
            return

        instruments_by_ticker = {}
        for instrument in instruments:
            instruments_by_ticker.setdefault(instrument.ticker, instrument)

        existing_by_ticker = {
            share.ticker: share
            for share in Share.objects.filter(ticker__in=instruments_by_ticker)
        }
        to_create = []
        to_update = []
        for instrument in instruments_by_ticker.values():
            share = existing_by_ticker.get(instrument.ticker)
            if share is None:
                to_create.append(
                    Share(
                        figi=instrument.figi,
                        isin=instrument.isin,
                        name=instrument.name,
                        ticker=instrument.ticker,
                        currency=instrument.currency,
                        uid=instrument.uid,
                    )
                )
                continue

            share.figi = instrument.figi
            share.isin = instrument.isin
            share.name = instrument.name
            share.currency = instrument.currency
            share.uid = instrument.uid
            to_update.append(share)

        if to_update:
            Share.objects.bulk_update(
                to_update, ("figi", "isin", "name", "currency", "uid")
            )
        Share.objects.bulk_create(
            to_create,
            ignore_conflicts=True,
            batch_size=500,
        )

        imported_shares = list(
            Share.objects.filter(ticker__in=instruments_by_ticker)
        )
        quotes = provider.get_quotes(imported_shares)
        for share in imported_shares:
            quote = quotes.get(share.figi)
            if quote is not None:
                previous_price = share.last_price
                share.last_price = quote.price
                share.updated_at = quote.observed_at
                share.is_trend_high = (
                    previous_price is None
                    or quote.price >= Decimal(str(previous_price))
                )
        if quotes:
            Share.objects.bulk_update(
                [
                    share
                    for share in imported_shares
                    if share.figi in quotes
                ],
                ("last_price", "updated_at", "is_trend_high"),
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {len(imported_shares)} shares and updated "
                f"{len(quotes)} prices."
            )
        )
