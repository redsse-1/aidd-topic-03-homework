from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from dashboard.models import InvestmentStrategy, SimulatedTrade

CENT = Decimal("0.01")


class NoPriceHistoryError(Exception):
    pass


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@transaction.atomic
def run_strategy(strategy_id: int) -> InvestmentStrategy:
    strategy = (
        InvestmentStrategy.objects.select_for_update()
        .select_related("share")
        .get(pk=strategy_id)
    )
    history = list(strategy.share.price_history.order_by("date"))
    if not history:
        raise NoPriceHistoryError("Для акции ещё нет истории дневных цен.")

    strategy.trades.all().delete()
    cash = strategy.initial_cash
    position = 0
    trades = []

    for point in history:
        if position == 0 and point.close <= strategy.buy_below:
            cost = _money(point.close * strategy.quantity)
            if cash >= cost:
                cash -= cost
                position = strategy.quantity
                trades.append(
                    SimulatedTrade(
                        strategy=strategy,
                        date=point.date,
                        side=SimulatedTrade.Side.BUY,
                        price=point.close,
                        quantity=strategy.quantity,
                        amount=cost,
                    )
                )
        elif position and point.close >= strategy.sell_at_or_above:
            proceeds = _money(point.close * position)
            cash += proceeds
            trades.append(
                SimulatedTrade(
                    strategy=strategy,
                    date=point.date,
                    side=SimulatedTrade.Side.SELL,
                    price=point.close,
                    quantity=position,
                    amount=proceeds,
                )
            )
            position = 0

    SimulatedTrade.objects.bulk_create(trades, batch_size=1000)
    last_price = history[-1].close
    ending_cash = _money(cash)
    ending_equity = _money(cash + last_price * position)
    return_percent = (
        (ending_equity - strategy.initial_cash)
        / strategy.initial_cash
        * Decimal("100")
    ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    strategy.last_run_at = timezone.now()
    strategy.simulated_until = history[-1].date
    strategy.ending_cash = ending_cash
    strategy.ending_equity = ending_equity
    strategy.return_percent = return_percent
    strategy.open_quantity = position
    strategy.save(
        update_fields=(
            "last_run_at",
            "simulated_until",
            "ending_cash",
            "ending_equity",
            "return_percent",
            "open_quantity",
            "updated_at",
        )
    )
    return strategy
