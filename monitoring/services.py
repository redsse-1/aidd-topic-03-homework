import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction

from .models import Notification, PriceTarget

logger = logging.getLogger(__name__)

HUNDRED = Decimal("100")


def is_reached(target, price):
    if target.direction == PriceTarget.Direction.ABOVE:
        return price >= target.target_price
    return price <= target.target_price


def has_left_level(target, price):
    """Проверить, что цена ушла за уровень с запасом: колебания около него не считаются"""
    band = target.target_price * Decimal(str(settings.MONITORING_REARM_PERCENT)) / HUNDRED
    if target.direction == PriceTarget.Direction.ABOVE:
        return price < target.target_price - band
    return price > target.target_price + band


def check_price_targets():
    """Сверить активные уровни с текущими ценами и создать уведомления о новых событиях.

    Повторный вызов с той же ценой ничего не меняет. Блокировка строк не даёт
    параллельным запускам обработать одно событие дважды.
    """
    changed = []
    notifications = []

    with transaction.atomic():
        targets = (
            PriceTarget.objects.select_for_update(of=("self",))
            .filter(is_active=True, item__share__last_price__isnull=False)
            .select_related("item__watchlist", "item__share")
        )
        for target in targets:
            share = target.item.share
            price = Decimal(str(share.last_price))

            if target.is_triggered:
                if has_left_level(target, price):
                    target.is_triggered = False
                    changed.append(target)
            elif is_reached(target, price):
                target.is_triggered = True
                target.events_count += 1
                changed.append(target)
                notifications.append(
                    Notification(
                        owner=target.item.watchlist.owner,
                        share=share,
                        target=target,
                        event_number=target.events_count,
                        direction=target.direction,
                        target_price=target.target_price,
                        price=price,
                    )
                )

        PriceTarget.objects.bulk_update(changed, ["is_triggered", "events_count"])
        Notification.objects.bulk_create(notifications)

    if notifications:
        logger.info("Создано уведомлений: %s", len(notifications))
    return len(notifications)
