import logging
from decimal import Decimal

from django.utils import timezone

from config.celery import app
from dashboard.models import Share, SharePriceHistory
from dashboard.services.market_data import get_market_data_provider
from dashboard.services.price_monitor import evaluate_price_alerts
from dashboard.services.price_history import quote_market_date, upsert_price_history

logger = logging.getLogger(__name__)


@app.task
def update_last_price() -> int:
    shares = list(Share.objects.all())
    if not shares:
        return 0

    quotes = get_market_data_provider().get_quotes(shares)
    updated_shares = []
    history_entries = []
    for share in shares:
        quote = quotes.get(share.figi)
        if quote is None:
            logger.warning("No market quote returned for %s", share.ticker)
            continue

        previous_price = (
            Decimal(str(share.last_price)) if share.last_price is not None else None
        )
        share.is_trend_high = previous_price is None or quote.price >= previous_price
        share.last_price = quote.price
        share.updated_at = quote.observed_at or timezone.now()
        updated_shares.append(share)
        history_entries.append(
            SharePriceHistory(
                share=share,
                date=quote_market_date(quote.observed_at),
                close=quote.price,
            )
        )

    if updated_shares:
        Share.objects.bulk_update(
            updated_shares, ("last_price", "is_trend_high", "updated_at")
        )
        upsert_price_history(history_entries)
        for share in updated_shares:
            quote = quotes[share.figi]
            evaluate_price_alerts(
                share.pk, quote.price, observed_at=quote.observed_at
            )
    return len(updated_shares)
