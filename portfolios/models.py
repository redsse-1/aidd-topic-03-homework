from decimal import Decimal

from django.conf import settings
from django.db import models

from dashboard.models import Share


class Portfolio(models.Model):
    """Виртуальный инвестиционный портфель пользователя"""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="portfolios"
    )
    name = models.CharField(max_length=100, verbose_name="Название")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Портфель"
        verbose_name_plural = "Портфели"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "name"], name="unique_portfolio_name"
            )
        ]

    def __str__(self):
        return self.name


class Position(models.Model):
    """Позиция по акции. Строка остаётся после продажи: в ней накоплена прибыль."""

    portfolio = models.ForeignKey(
        Portfolio, on_delete=models.CASCADE, related_name="positions"
    )
    share = models.ForeignKey(
        Share, on_delete=models.CASCADE, related_name="positions"
    )
    quantity = models.PositiveBigIntegerField(default=0)
    average_price = models.DecimalField(
        max_digits=30, decimal_places=8, default=Decimal("0")
    )
    realized_profit = models.DecimalField(
        max_digits=30, decimal_places=2, default=Decimal("0")
    )

    class Meta:
        verbose_name = "Позиция"
        verbose_name_plural = "Позиции"
        ordering = ["share__ticker"]
        constraints = [
            models.UniqueConstraint(
                fields=["portfolio", "share"], name="unique_portfolio_share"
            )
        ]

    def __str__(self):
        return f"{self.portfolio}: {self.share.ticker} {self.quantity}"


class Operation(models.Model):
    """Виртуальная операция. Записи журнала не меняются и не удаляются по отдельности."""

    class Side(models.TextChoices):
        BUY = "buy", "Покупка"
        SELL = "sell", "Продажа"

    portfolio = models.ForeignKey(
        Portfolio, on_delete=models.CASCADE, related_name="operations"
    )
    share = models.ForeignKey(
        Share, on_delete=models.CASCADE, related_name="operations"
    )
    side = models.CharField(max_length=4, choices=Side.choices, verbose_name="Операция")
    quantity = models.PositiveBigIntegerField(verbose_name="Количество")
    price = models.DecimalField(max_digits=30, decimal_places=6)
    amount = models.DecimalField(max_digits=30, decimal_places=2)
    realized_profit = models.DecimalField(
        max_digits=30, decimal_places=2, blank=True, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Операция"
        verbose_name_plural = "Операции"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["portfolio", "-created_at"])]

    def __str__(self):
        return f"{self.side} {self.share_id} {self.quantity}"
