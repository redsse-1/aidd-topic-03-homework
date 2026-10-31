from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from dashboard.models import Share

from .models import Operation, Portfolio, Position

CENT = Decimal("0.01")
AVERAGE_STEP = Decimal("0.00000001")
HUNDRED = Decimal("100")


class OperationError(Exception):
    """Операцию нельзя выполнить. Текст показывается пользователю."""


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def current_price(share):
    """Вернуть цену акции для операции или сообщить, что цены нет"""
    if not share.last_price or share.last_price <= 0:
        raise OperationError(f"У акции {share.ticker} нет текущей цены")
    return Decimal(str(share.last_price))


def apply_buy(position, quantity, price):
    """Пересчитать среднюю цену как среднюю, взвешенную по количеству"""
    total_quantity = position.quantity + quantity
    total_cost = position.average_price * position.quantity + price * quantity
    position.average_price = (total_cost / total_quantity).quantize(
        AVERAGE_STEP, rounding=ROUND_HALF_UP
    )
    position.quantity = total_quantity


def apply_sell(position, quantity, price):
    """Зафиксировать прибыль. Средняя цена оставшихся акций при продаже не меняется."""
    profit = money((price - position.average_price) * quantity)
    position.quantity -= quantity
    position.realized_profit += profit
    if position.quantity == 0:
        position.average_price = Decimal("0")
    return profit


def execute_operation(portfolio, share, side, quantity):
    """Выполнить операцию по текущей цене из БД.

    Блокировка портфеля выстраивает операции в очередь: иначе параллельные продажи
    могли бы вместе превысить количество акций в позиции.
    """
    if quantity <= 0:
        raise OperationError("Количество должно быть положительным")

    with transaction.atomic():
        Portfolio.objects.select_for_update().get(pk=portfolio.pk)
        share = Share.objects.get(pk=share.pk)
        price = current_price(share)

        realized = None
        if side == Operation.Side.BUY:
            position, _ = Position.objects.get_or_create(portfolio=portfolio, share=share)
            apply_buy(position, quantity, price)
        else:
            position = Position.objects.filter(portfolio=portfolio, share=share).first()
            held = position.quantity if position else 0
            if quantity > held:
                raise OperationError(
                    f"Нельзя продать {quantity} шт.: в портфеле {held} шт. {share.ticker}"
                )
            realized = apply_sell(position, quantity, price)

        position.save()
        return Operation.objects.create(
            portfolio=portfolio,
            share=share,
            side=side,
            quantity=quantity,
            price=price,
            amount=money(price * quantity),
            realized_profit=realized,
        )


@dataclass
class PositionRow:
    """Открытая позиция с оценкой по текущей цене"""

    position: Position
    price: Decimal | None
    cost: Decimal
    market_value: Decimal | None
    unrealized: Decimal | None
    unrealized_percent: Decimal | None


@dataclass
class Summary:
    """Оценка портфеля. Позиции без цены в стоимость и нереализованную прибыль не входят."""

    rows: list
    closed: list
    cost: Decimal
    market_value: Decimal
    unrealized: Decimal
    unrealized_percent: Decimal | None
    realized: Decimal
    total_profit: Decimal
    unpriced: int


def make_row(position):
    share = position.share
    cost = money(position.average_price * position.quantity)
    if not share.last_price:
        return PositionRow(position, None, cost, None, None, None)

    price = Decimal(str(share.last_price))
    market_value = money(price * position.quantity)
    unrealized = market_value - cost
    percent = money(unrealized / cost * HUNDRED) if cost else None
    return PositionRow(position, price, cost, market_value, unrealized, percent)


def summarize(positions):
    """Посчитать стоимость и прибыль по списку позиций портфеля"""
    rows = [make_row(position) for position in positions if position.quantity]
    closed = [position for position in positions if not position.quantity]
    priced = [row for row in rows if row.price is not None]

    cost = sum((row.cost for row in priced), Decimal("0"))
    market_value = sum((row.market_value for row in priced), Decimal("0"))
    unrealized = market_value - cost
    realized = sum((position.realized_profit for position in positions), Decimal("0"))
    return Summary(
        rows=rows,
        closed=closed,
        cost=cost,
        market_value=market_value,
        unrealized=unrealized,
        unrealized_percent=money(unrealized / cost * HUNDRED) if cost else None,
        realized=realized,
        total_profit=unrealized + realized,
        unpriced=len(rows) - len(priced),
    )
