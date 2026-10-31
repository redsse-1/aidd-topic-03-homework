import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from dashboard.models import Share

logger = logging.getLogger(__name__)


def compute_trend(old_price, new_price, current_trend):
    """Определить тренд. Без прежней цены он неизвестен, равная цена его не меняет."""
    if old_price is None:
        return None
    if new_price == old_price:
        return current_trend
    return new_price > old_price


def update_last_prices(provider):
    """Обновить цены и тренд всех акций одним запросом к провайдеру"""
    shares = list(Share.objects.all())
    prices = provider.get_last_prices(shares)
    updated_at = timezone.now()

    updated = []
    for share in shares:
        price = prices.get(share.ticker)
        if price is None:
            continue
        share.is_trend_high = compute_trend(
            share.last_price, price, share.is_trend_high
        )
        share.last_price = price
        share.updated_at = updated_at
        updated.append(share)

    Share.objects.bulk_update(updated, ["last_price", "is_trend_high", "updated_at"])
    logger.info("Цены обновлены: %s из %s", len(updated), len(shares))
    return len(updated)


def sync_shares(provider):
    """Загрузить справочник акций. Запись определяется тикером, общим для всех источников."""
    saved = 0
    for instrument in provider.list_shares():
        try:
            with transaction.atomic():
                Share.objects.update_or_create(
                    ticker=instrument.ticker,
                    defaults={
                        "figi": instrument.figi,
                        "isin": instrument.isin,
                        "name": instrument.name,
                        "currency": instrument.currency,
                        "uid": instrument.uid,
                    },
                )
            saved += 1
        except IntegrityError as e:
            logger.error("Акция %s не сохранена: %s", instrument.ticker, e)
    return saved
