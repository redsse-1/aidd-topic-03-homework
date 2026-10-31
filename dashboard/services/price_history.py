import logging
import time as time_module
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.conf import settings
from django.utils import timezone

from dashboard.models import PriceRecord, Share

from .market_data import MarketDataError

logger = logging.getLogger(__name__)

# До такой длины периода показываются внутридневные котировки
DETAILED_RANGE_DAYS = 7
REFRESH_DAYS = 7


@dataclass(frozen=True)
class PricePoint:
    """Точка истории цены"""

    moment: datetime
    price: float

    @property
    def date(self):
        return timezone.localdate(self.moment)


def record_quotes(shares, quotes):
    """Сохранить котировки со временем сделки. Повтор той же сделки не создаёт записи."""
    records = [
        PriceRecord(
            share=share,
            kind=PriceRecord.Kind.QUOTE,
            recorded_at=quotes[share.ticker].time,
            price=quotes[share.ticker].price,
        )
        for share in shares
        if share.ticker in quotes and quotes[share.ticker].time is not None
    ]
    PriceRecord.objects.bulk_create(records, ignore_conflicts=True)


def save_daily_candles(share, candles):
    """Сохранить завершённые дневные свечи: сегодняшняя свеча ещё меняется"""
    today = timezone.localdate()
    records = [
        PriceRecord(
            share=share,
            kind=PriceRecord.Kind.DAILY,
            recorded_at=timezone.make_aware(datetime.combine(candle.date, time.min)),
            price=candle.close,
        )
        for candle in candles
        if candle.date < today
    ]
    PriceRecord.objects.bulk_create(
        records,
        update_conflicts=True,
        unique_fields=["share", "kind", "recorded_at"],
        update_fields=["price"],
    )
    return len(records)


def backfill_history(provider, shares, days, pause=0.0):
    """Заполнить историю из дневных свечей. Ошибка по одной акции не прерывает остальные."""
    saved = failed = 0
    for share in shares:
        try:
            saved += save_daily_candles(
                share, provider.get_daily_candles(share, days(share))
            )
        except MarketDataError as e:
            failed += 1
            logger.error("История %s не загружена: %s", share.ticker, e)
        if pause:
            time_module.sleep(pause)
    return saved, failed


def refresh_daily_history(provider):
    """Догрузить последние дни, а для акций без истории загрузить её целиком"""
    with_history = set(
        PriceRecord.objects.filter(kind=PriceRecord.Kind.DAILY)
        .values_list("share_id", flat=True)
        .distinct()
    )

    def days(share):
        return REFRESH_DAYS if share.id in with_history else settings.HISTORY_BACKFILL_DAYS

    saved, failed = backfill_history(
        provider, Share.objects.all(), days, settings.HISTORY_REQUEST_PAUSE
    )
    logger.info("Дневная история: записей %s, ошибок %s", saved, failed)
    return saved, failed


def prune_quotes():
    """Удалить старые внутридневные котировки: дневные закрытия остаются навсегда"""
    border = timezone.now() - timedelta(days=settings.HISTORY_QUOTE_RETENTION_DAYS)
    deleted, _ = PriceRecord.objects.filter(
        kind=PriceRecord.Kind.QUOTE, recorded_at__lt=border
    ).delete()
    return deleted


def day_start(day):
    return timezone.make_aware(datetime.combine(day, time.min))


def get_series(share, start, end):
    """Вернуть точки за даты start..end. Без start — всю историю.

    Для дня берётся закрытие, а котировки — если закрытия ещё нет или период короткий.
    """
    records = share.price_records.filter(recorded_at__lt=day_start(end + timedelta(days=1)))
    if start is not None:
        records = records.filter(recorded_at__gte=day_start(start))

    daily = {}
    quotes = defaultdict(list)
    for kind, moment, price in records.order_by("recorded_at").values_list(
        "kind", "recorded_at", "price"
    ):
        point = PricePoint(moment, price)
        if kind == PriceRecord.Kind.DAILY:
            daily[point.date] = point
        else:
            quotes[point.date].append(point)

    detailed = start is not None and (end - start).days <= DETAILED_RANGE_DAYS
    points = []
    for day in sorted(daily.keys() | quotes.keys()):
        if day in quotes and (detailed or day not in daily):
            points += quotes[day]
        else:
            points.append(daily[day])
    return points


def change_between(old, new):
    """Вернуть абсолютное и процентное изменение цены"""
    change = round(new - old, 6)
    return change, round(change / old * 100, 4) if old else None


def daily_changes(points):
    """Вернуть изменения по дням, новые сверху. Для дня берётся его последняя цена."""
    last_by_day = {point.date: point.price for point in points}
    rows = []
    previous = None
    for day, price in sorted(last_by_day.items()):
        change, percent = (None, None)
        if previous is not None:
            change, percent = change_between(previous, price)
        rows.append({"date": day, "price": price, "change": change, "percent": percent})
        previous = price
    return rows[::-1]


def compute_stats(points):
    """Посчитать показатели динамики за период или вернуть None, если точек нет"""
    if not points:
        return None

    first, last = points[0], points[-1]
    lowest = min(points, key=lambda point: point.price)
    highest = max(points, key=lambda point: point.price)
    change, percent = change_between(first.price, last.price)
    changes = [row["change"] for row in daily_changes(points) if row["change"]]
    return {
        "first_price": first.price,
        "first_date": first.date,
        "last_price": last.price,
        "last_date": last.date,
        "change": change,
        "percent": percent,
        "min_price": lowest.price,
        "min_date": lowest.date,
        "max_price": highest.price,
        "max_date": highest.date,
        "average": round(sum(point.price for point in points) / len(points), 6),
        "up_days": sum(1 for value in changes if value > 0),
        "down_days": sum(1 for value in changes if value < 0),
        "points": len(points),
    }
