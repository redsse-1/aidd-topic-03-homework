from datetime import date, datetime
from decimal import Decimal
from typing import Iterable
from zoneinfo import ZoneInfo

from django.utils import timezone

from dashboard.models import Share, SharePriceHistory

MOSCOW = ZoneInfo("Europe/Moscow")


def upsert_price_history(
    entries: Iterable[SharePriceHistory],
) -> int:
    entries_by_key = {
        (entry.share_id, entry.date): entry
        for entry in entries
    }
    if not entries_by_key:
        return 0

    updated_at = timezone.now()
    records = list(entries_by_key.values())
    for record in records:
        record.updated_at = updated_at

    SharePriceHistory.objects.bulk_create(
        records,
        batch_size=1000,
        update_conflicts=True,
        update_fields=("close", "updated_at"),
        unique_fields=("share", "date"),
    )
    return len(records)


def upsert_share_prices(
    share: Share, prices: Iterable[tuple[date, Decimal]]
) -> int:
    return upsert_price_history(
        SharePriceHistory(share=share, date=price_date, close=price)
        for price_date, price in prices
    )


def quote_market_date(observed_at: datetime) -> date:
    if timezone.is_naive(observed_at):
        observed_at = timezone.make_aware(observed_at, MOSCOW)
    return observed_at.astimezone(MOSCOW).date()
