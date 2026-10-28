from django.db import transaction
from django.utils import timezone

from dashboard.models import PriceNotification, WatchlistEntry


def _is_reached(entry: WatchlistEntry, price) -> bool:
    if entry.direction == WatchlistEntry.Direction.AT_OR_ABOVE:
        return price >= entry.target_price
    return price <= entry.target_price


@transaction.atomic
def evaluate_price_alerts(share_id: int, price, observed_at=None) -> int:
    observed_at = observed_at or timezone.now()
    entries = (
        WatchlistEntry.objects.select_for_update()
        .select_related("share", "watchlist")
        .filter(share_id=share_id, watchlist__owner__is_active=True)
        .order_by("pk")
    )
    created = 0
    for entry in entries:
        reached = _is_reached(entry, price)
        if reached and not entry.is_triggered:
            direction_label = entry.get_direction_display().lower()
            PriceNotification.objects.create(
                entry=entry,
                triggered_price=price,
                triggered_at=observed_at,
                message=(
                    f"{entry.share.ticker}: цена {price} достигла целевого уровня "
                    f"{entry.target_price} ({direction_label})."
                ),
            )
            created += 1
        entry.is_triggered = reached
        entry.last_checked_price = price
        entry.last_checked_at = observed_at
        entry.save(
            update_fields=(
                "is_triggered",
                "last_checked_price",
                "last_checked_at",
            )
        )
    return created
