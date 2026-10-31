import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from dashboard.models import PriceRecord

from .engine import SimulationError, simulate
from .models import SimulationResult, Strategy, VirtualTrade

logger = logging.getLogger(__name__)


def load_closes(strategy):
    """Вернуть дневные закрытия акции до конца периода и индекс начала периода"""
    records = strategy.share.price_records.filter(kind=PriceRecord.Kind.DAILY)
    closes = [
        (timezone.localdate(moment), Decimal(str(price)))
        for moment, price in records.order_by("recorded_at").values_list(
            "recorded_at", "price"
        )
    ]
    if strategy.date_to:
        closes = [item for item in closes if item[0] <= strategy.date_to]

    start = 0
    if strategy.date_from:
        start = sum(1 for day, _ in closes if day < strategy.date_from)
    return closes, start


def run_simulation(strategy):
    """Рассчитать стратегию и заменить её прежний результат"""
    outcome = simulate(strategy, *load_closes(strategy))

    with transaction.atomic():
        Strategy.objects.select_for_update().get(pk=strategy.pk)
        SimulationResult.objects.filter(strategy=strategy).delete()
        result = SimulationResult.objects.create(
            strategy=strategy,
            period_start=outcome.period_start,
            period_end=outcome.period_end,
            final_value=outcome.final_value,
            profit=outcome.profit,
            return_percent=outcome.return_percent,
            buy_hold_percent=outcome.buy_hold_percent,
            max_drawdown_percent=outcome.max_drawdown_percent,
            closed_trades=outcome.closed_trades,
            winning_trades=outcome.winning_trades,
            total_commission=outcome.total_commission,
            open_quantity=outcome.open_quantity,
            skipped_signals=outcome.skipped_signals,
            equity=[[day.isoformat(), str(value)] for day, value in outcome.equity],
        )
        VirtualTrade.objects.bulk_create(
            VirtualTrade(
                result=result,
                signal_date=trade.signal_date,
                date=trade.date,
                side=trade.side,
                price=trade.price,
                quantity=trade.quantity,
                amount=trade.amount,
                commission=trade.commission,
                cash_after=trade.cash_after,
                profit=trade.profit,
                reason=trade.reason,
            )
            for trade in outcome.trades
        )
    return result


def update_auto_strategies():
    """Пересчитать стратегии с автообновлением. Ошибка одной не мешает остальным."""
    updated = 0
    strategies = Strategy.objects.filter(auto_update=True).select_related("share")
    for strategy in strategies:
        try:
            run_simulation(strategy)
            updated += 1
        except SimulationError as e:
            logger.warning("Стратегия %s не рассчитана: %s", strategy.pk, e)
    logger.info("Стратегий пересчитано: %s", updated)
    return updated
