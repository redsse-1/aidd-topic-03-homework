"""Моделирование стратегии по дневным закрытиям. Модуль не работает с БД.

Сигнал считается по закрытию дня, а сделка исполняется по закрытию следующего дня:
в момент решения закрытие того же дня ещё неизвестно. Позиция одна, только длинная.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from .conditions import BuyCondition, SellCondition

CENT = Decimal("0.01")
HUNDRED = Decimal("100")
MIN_POINTS = 2


class SimulationError(Exception):
    """Моделирование невозможно: не хватает данных"""


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Trade:
    signal_date: date
    date: date
    side: str
    price: Decimal
    quantity: int
    amount: Decimal
    commission: Decimal
    cash_after: Decimal
    profit: Decimal | None
    reason: str


@dataclass
class Outcome:
    period_start: date
    period_end: date
    final_value: Decimal
    profit: Decimal
    return_percent: Decimal
    buy_hold_percent: Decimal
    max_drawdown_percent: Decimal
    closed_trades: int
    winning_trades: int
    total_commission: Decimal
    open_quantity: int
    skipped_signals: int
    trades: list = field(default_factory=list)
    equity: list = field(default_factory=list)


def sma(prices, index, window):
    """Вернуть среднюю за window дней по index включительно или None, если дней мало"""
    if index + 1 < window:
        return None
    return sum(prices[index + 1 - window : index + 1]) / window


def sma_difference(strategy, prices, index):
    short = sma(prices, index, strategy.sma_short)
    long = sma(prices, index, strategy.sma_long)
    if short is None or long is None:
        return None
    return short - long


def crossed(strategy, prices, index, upwards):
    if index == 0:
        return False
    previous = sma_difference(strategy, prices, index - 1)
    current = sma_difference(strategy, prices, index)
    if previous is None or current is None:
        return False
    if upwards:
        return previous <= 0 < current
    return previous >= 0 > current


def buy_reason(strategy, prices, index):
    """Вернуть причину покупки или None, если условие не выполнено"""
    price = prices[index]
    if strategy.buy_condition == BuyCondition.PRICE_BELOW:
        if price <= strategy.buy_value:
            return f"Цена {price} не выше {strategy.buy_value.normalize():f}"
    elif strategy.buy_condition == BuyCondition.DROP_FROM_HIGH:
        window = prices[max(0, index + 1 - strategy.lookback_days) : index + 1]
        high = max(window)
        if price <= high * (1 - strategy.buy_value / HUNDRED):
            return (
                f"Падение от максимума {high} на {strategy.buy_value.normalize():f}% "
                f"и более"
            )
    elif crossed(strategy, prices, index, upwards=True):
        return f"Средняя {strategy.sma_short} пересекла {strategy.sma_long} снизу вверх"
    return None


def sell_reason(strategy, prices, index, entry_price):
    """Вернуть причину продажи или None. Стоп-лосс проверяется первым."""
    price = prices[index]
    if strategy.stop_loss_percent is not None:
        if price <= entry_price * (1 - strategy.stop_loss_percent / HUNDRED):
            return f"Стоп-лосс {strategy.stop_loss_percent.normalize():f}%"

    if strategy.sell_condition == SellCondition.PRICE_ABOVE:
        if price >= strategy.sell_value:
            return f"Цена {price} не ниже {strategy.sell_value.normalize():f}"
    elif strategy.sell_condition == SellCondition.TAKE_PROFIT:
        if price >= entry_price * (1 + strategy.sell_value / HUNDRED):
            return f"Рост от покупки на {strategy.sell_value.normalize():f}% и более"
    elif crossed(strategy, prices, index, upwards=False):
        return f"Средняя {strategy.sma_short} пересекла {strategy.sma_long} сверху вниз"
    return None


def max_drawdown(values):
    """Вернуть наибольшее падение стоимости от её предыдущего максимума, %"""
    peak = values[0]
    worst = Decimal("0")
    for value in values:
        peak = max(peak, value)
        if peak:
            worst = max(worst, (peak - value) / peak * HUNDRED)
    return money(worst)


def simulate(strategy, closes, start=0):
    """Смоделировать стратегию по списку (дата, цена) от индекса start.

    Дни до start участвуют только в расчёте показателей: средних и максимума.
    """
    if len(closes) - start < MIN_POINTS:
        raise SimulationError("Для моделирования нужно минимум два дня истории цен")

    dates = [day for day, _ in closes]
    prices = [price for _, price in closes]
    rate = strategy.commission_percent / HUNDRED

    cash = strategy.initial_capital
    quantity = 0
    entry_price = None
    cost_basis = Decimal("0")
    pending = None
    trades = []
    equity = []
    closed = winning = skipped = 0
    total_commission = Decimal("0")

    for index in range(start, len(closes)):
        day, price = dates[index], prices[index]

        if pending:
            side, signal_date, reason = pending
            pending = None
            if side == "buy":
                affordable = int(cash / (price * (1 + rate)))
                amount = money(price * affordable)
                commission = money(amount * rate)
                if affordable and amount + commission > cash:
                    affordable -= 1
                    amount = money(price * affordable)
                    commission = money(amount * rate)
                if affordable:
                    quantity = affordable
                    entry_price = price
                    cost_basis = amount + commission
                    cash -= cost_basis
                    total_commission += commission
                    trades.append(
                        Trade(
                            signal_date, day, "buy", price, quantity, amount,
                            commission, cash, None, reason,
                        )
                    )
                else:
                    skipped += 1
            else:
                amount = money(price * quantity)
                commission = money(amount * rate)
                proceeds = amount - commission
                profit = proceeds - cost_basis
                cash += proceeds
                total_commission += commission
                closed += 1
                winning += profit > 0
                trades.append(
                    Trade(
                        signal_date, day, "sell", price, quantity, amount,
                        commission, cash, profit, reason,
                    )
                )
                quantity = 0
                entry_price = None

        equity.append((day, money(cash + price * quantity)))

        if index == len(closes) - 1:
            break
        if quantity:
            reason = sell_reason(strategy, prices, index, entry_price)
            if reason:
                pending = ("sell", day, reason)
        else:
            reason = buy_reason(strategy, prices, index)
            if reason:
                pending = ("buy", day, reason)

    final_value = equity[-1][1]
    first_price, last_price = prices[start], prices[-1]
    profit = final_value - strategy.initial_capital
    return Outcome(
        period_start=dates[start],
        period_end=dates[-1],
        final_value=final_value,
        profit=profit,
        return_percent=money(profit / strategy.initial_capital * HUNDRED),
        buy_hold_percent=money((last_price / first_price - 1) * HUNDRED),
        max_drawdown_percent=max_drawdown([value for _, value in equity]),
        closed_trades=closed,
        winning_trades=winning,
        total_commission=total_commission,
        open_quantity=quantity,
        skipped_signals=skipped,
        trades=trades,
        equity=equity,
    )
