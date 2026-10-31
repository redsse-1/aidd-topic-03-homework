from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from dashboard.models import Share

from .conditions import BuyCondition, SellCondition


class Strategy(models.Model):
    """Стратегия пользователя: условия покупки и продажи одной акции"""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="strategies"
    )
    name = models.CharField(max_length=100, verbose_name="Название")
    share = models.ForeignKey(
        Share,
        on_delete=models.CASCADE,
        related_name="strategies",
        verbose_name="Акция",
    )
    initial_capital = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("100000"),
        validators=[MinValueValidator(Decimal("1"))],
        verbose_name="Начальный капитал",
    )
    commission_percent = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        default=Decimal("0.05"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("10"))],
        verbose_name="Комиссия за сделку, %",
    )
    buy_condition = models.CharField(
        max_length=20, choices=BuyCondition.choices, verbose_name="Условие покупки"
    )
    buy_value = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.000001"))],
        verbose_name="Значение для покупки",
    )
    sell_condition = models.CharField(
        max_length=20, choices=SellCondition.choices, verbose_name="Условие продажи"
    )
    sell_value = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.000001"))],
        verbose_name="Значение для продажи",
    )
    stop_loss_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.01")), MaxValueValidator(Decimal("99"))],
        verbose_name="Стоп-лосс, %",
    )
    lookback_days = models.PositiveSmallIntegerField(
        default=20,
        validators=[MinValueValidator(2)],
        verbose_name="Период поиска максимума, торговых дней",
    )
    sma_short = models.PositiveSmallIntegerField(
        default=10,
        validators=[MinValueValidator(2)],
        verbose_name="Короткая средняя, дней",
    )
    sma_long = models.PositiveSmallIntegerField(
        default=30,
        validators=[MinValueValidator(3)],
        verbose_name="Длинная средняя, дней",
    )
    date_from = models.DateField(blank=True, null=True, verbose_name="Начало моделирования")
    date_to = models.DateField(blank=True, null=True, verbose_name="Конец моделирования")
    auto_update = models.BooleanField(
        default=True, verbose_name="Пересчитывать каждую ночь"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Стратегия"
        verbose_name_plural = "Стратегии"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class SimulationResult(models.Model):
    """Результат последнего моделирования стратегии"""

    strategy = models.OneToOneField(
        Strategy, on_delete=models.CASCADE, related_name="result"
    )
    calculated_at = models.DateTimeField(auto_now_add=True)
    period_start = models.DateField()
    period_end = models.DateField()
    final_value = models.DecimalField(max_digits=18, decimal_places=2)
    profit = models.DecimalField(max_digits=18, decimal_places=2)
    return_percent = models.DecimalField(max_digits=12, decimal_places=2)
    buy_hold_percent = models.DecimalField(max_digits=12, decimal_places=2)
    max_drawdown_percent = models.DecimalField(max_digits=7, decimal_places=2)
    closed_trades = models.PositiveIntegerField()
    winning_trades = models.PositiveIntegerField()
    total_commission = models.DecimalField(max_digits=18, decimal_places=2)
    open_quantity = models.PositiveBigIntegerField()
    skipped_signals = models.PositiveIntegerField()
    equity = models.JSONField()

    class Meta:
        verbose_name = "Результат моделирования"
        verbose_name_plural = "Результаты моделирования"

    @property
    def win_rate(self):
        if not self.closed_trades:
            return None
        return self.winning_trades / self.closed_trades * 100


class VirtualTrade(models.Model):
    """Виртуальная операция в журнале стратегии"""

    class Side(models.TextChoices):
        BUY = "buy", "Покупка"
        SELL = "sell", "Продажа"

    result = models.ForeignKey(
        SimulationResult, on_delete=models.CASCADE, related_name="trades"
    )
    signal_date = models.DateField()
    date = models.DateField()
    side = models.CharField(max_length=4, choices=Side.choices)
    price = models.DecimalField(max_digits=18, decimal_places=6)
    quantity = models.PositiveBigIntegerField()
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    commission = models.DecimalField(max_digits=18, decimal_places=2)
    cash_after = models.DecimalField(max_digits=18, decimal_places=2)
    profit = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True)
    reason = models.CharField(max_length=255)

    class Meta:
        verbose_name = "Виртуальная операция"
        verbose_name_plural = "Виртуальные операции"
        ordering = ["date", "id"]
