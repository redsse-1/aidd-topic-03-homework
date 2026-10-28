from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from dashboard.models import (
    InvestmentPortfolio,
    PortfolioPosition,
    PortfolioTransaction,
    Share,
)

CENT = Decimal("0.01")
PRICE_QUANTUM = Decimal("0.000000001")


class PortfolioOperationError(Exception):
    pass


def _money(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


@transaction.atomic
def execute_portfolio_transaction(
    portfolio_id: int,
    owner_id: int,
    share_id: int,
    side: str,
    quantity: Decimal,
) -> PortfolioTransaction:
    portfolio = (
        InvestmentPortfolio.objects.select_for_update()
        .filter(pk=portfolio_id, owner_id=owner_id)
        .first()
    )
    if portfolio is None:
        raise PortfolioOperationError("Портфель не найден.")

    share = Share.objects.select_for_update().filter(pk=share_id).first()
    if share is None:
        raise PortfolioOperationError("Акция не найдена.")
    if share.last_price is None or share.last_price <= 0:
        raise PortfolioOperationError("Для акции нет актуальной цены.")
    if quantity <= 0:
        raise PortfolioOperationError("Количество должно быть больше нуля.")
    if side not in PortfolioTransaction.Side.values:
        raise PortfolioOperationError("Неизвестный тип операции.")

    position = (
        PortfolioPosition.objects.select_for_update()
        .filter(portfolio=portfolio, share=share)
        .first()
    )
    if position is None:
        position = PortfolioPosition(portfolio=portfolio, share=share)

    price = share.last_price.quantize(PRICE_QUANTUM)
    amount = _money(price * quantity)
    realized_profit = Decimal("0.00")

    if side == PortfolioTransaction.Side.BUY:
        new_quantity = position.quantity + quantity
        position.average_cost = (
            (position.quantity * position.average_cost + quantity * price)
            / new_quantity
        ).quantize(PRICE_QUANTUM, rounding=ROUND_HALF_UP)
        position.quantity = new_quantity
    else:
        if quantity > position.quantity:
            raise PortfolioOperationError(
                "Нельзя продать больше акций, чем находится в портфеле."
            )
        realized_profit = _money((price - position.average_cost) * quantity)
        position.quantity -= quantity
        position.realized_profit += realized_profit
        if position.quantity == 0:
            position.average_cost = Decimal("0")

    position.updated_at = timezone.now()
    position.save()
    portfolio.updated_at = timezone.now()
    portfolio.save(update_fields=("updated_at",))

    return PortfolioTransaction.objects.create(
        portfolio=portfolio,
        share=share,
        side=side,
        quantity=quantity,
        price=price,
        amount=amount,
        realized_profit=realized_profit,
    )
