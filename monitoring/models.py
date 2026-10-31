from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from dashboard.models import Share


class Watchlist(models.Model):
    """Персональный список наблюдения"""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="watchlists"
    )
    name = models.CharField(max_length=100, verbose_name="Название")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Список наблюдения"
        verbose_name_plural = "Списки наблюдения"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "name"], name="unique_watchlist_name"
            )
        ]

    def __str__(self):
        return self.name


class WatchlistItem(models.Model):
    """Акция в списке наблюдения"""

    watchlist = models.ForeignKey(
        Watchlist, on_delete=models.CASCADE, related_name="items"
    )
    share = models.ForeignKey(
        Share, on_delete=models.CASCADE, related_name="watchlist_items"
    )

    class Meta:
        verbose_name = "Акция в списке"
        verbose_name_plural = "Акции в списках"
        ordering = ["share__ticker"]
        constraints = [
            models.UniqueConstraint(
                fields=["watchlist", "share"], name="unique_watchlist_share"
            )
        ]

    def __str__(self):
        return f"{self.watchlist}: {self.share.ticker}"


class PriceTarget(models.Model):
    """Целевой уровень цены.

    is_triggered означает, что о текущем достижении уровня уже сообщено.
    Новое уведомление возможно только после возврата цены за уровень.
    """

    class Direction(models.TextChoices):
        ABOVE = "above", "Цена поднимется до уровня"
        BELOW = "below", "Цена опустится до уровня"

    item = models.ForeignKey(
        WatchlistItem, on_delete=models.CASCADE, related_name="targets"
    )
    direction = models.CharField(
        max_length=5, choices=Direction.choices, verbose_name="Условие"
    )
    target_price = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("0.000001"))],
        verbose_name="Целевая цена",
    )
    is_active = models.BooleanField(default=True, verbose_name="Отслеживать")
    is_triggered = models.BooleanField(default=False, editable=False)
    events_count = models.PositiveIntegerField(default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Целевой уровень"
        verbose_name_plural = "Целевые уровни"
        ordering = ["target_price"]
        constraints = [
            models.UniqueConstraint(
                fields=["item", "direction", "target_price"],
                name="unique_price_target",
            )
        ]

    def __str__(self):
        return f"{self.item.share.ticker} {self.direction} {self.target_price}"


class Notification(models.Model):
    """Уведомление о достижении целевого уровня.

    Уведомление хранит значения на момент события: уровень можно изменить или удалить.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    share = models.ForeignKey(
        Share, on_delete=models.CASCADE, related_name="notifications"
    )
    target = models.ForeignKey(
        PriceTarget,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="notifications",
    )
    event_number = models.PositiveIntegerField()
    direction = models.CharField(max_length=5, choices=PriceTarget.Direction.choices)
    target_price = models.DecimalField(max_digits=18, decimal_places=6)
    price = models.DecimalField(max_digits=18, decimal_places=6)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["target", "event_number"], name="unique_target_event"
            )
        ]
        indexes = [models.Index(fields=["owner", "read_at"])]

    @property
    def event_text(self):
        if self.direction == PriceTarget.Direction.ABOVE:
            return "Цена поднялась до уровня"
        return "Цена опустилась до уровня"

    def __str__(self):
        return f"{self.share_id} {self.direction} {self.target_price}"
