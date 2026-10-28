from django.db import models
from django.conf import settings


class Share(models.Model):
    """Акция"""

    figi = models.CharField(max_length=255, unique=True)
    isin = models.CharField(max_length=255)
    name = models.CharField(max_length=255, verbose_name="Наименование компании")
    ticker = models.CharField(max_length=10, unique=True, verbose_name="Тикер")
    currency = models.CharField(max_length=20, verbose_name="Валюта")
    uid = models.CharField(max_length=255, unique=True)
    last_price = models.DecimalField(
        max_digits=20,
        decimal_places=9,
        blank=True,
        null=True,
        verbose_name="Текущая цена",
    )
    is_trend_high = models.BooleanField(
        blank=True, null=True, verbose_name="Растет цена"
    )
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)

    class Meta:
        verbose_name = "Акция"
        verbose_name_plural = "Акции"


class SharePriceHistory(models.Model):
    share = models.ForeignKey(
        Share,
        on_delete=models.CASCADE,
        related_name="price_history",
        verbose_name="Акция",
    )
    date = models.DateField(verbose_name="Дата")
    close = models.DecimalField(
        max_digits=20, decimal_places=9, verbose_name="Цена закрытия"
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        ordering = ("date",)
        verbose_name = "История цены"
        verbose_name_plural = "История цен"
        constraints = [
            models.UniqueConstraint(
                fields=("share", "date"), name="unique_share_price_history_date"
            )
        ]

    def __str__(self):
        return f"{self.share.ticker} {self.date}: {self.close}"


class InvestmentStrategy(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="investment_strategies",
    )
    share = models.ForeignKey(
        Share, on_delete=models.CASCADE, related_name="investment_strategies"
    )
    name = models.CharField(max_length=100)
    initial_cash = models.DecimalField(max_digits=20, decimal_places=2)
    quantity = models.PositiveIntegerField()
    buy_below = models.DecimalField(max_digits=20, decimal_places=9)
    sell_at_or_above = models.DecimalField(max_digits=20, decimal_places=9)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    simulated_until = models.DateField(null=True, blank=True)
    ending_cash = models.DecimalField(
        max_digits=20, decimal_places=2, null=True, blank=True
    )
    ending_equity = models.DecimalField(
        max_digits=20, decimal_places=2, null=True, blank=True
    )
    return_percent = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True
    )
    open_quantity = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-updated_at",)
        verbose_name = "Инвестиционная стратегия"
        verbose_name_plural = "Инвестиционные стратегии"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(initial_cash__gt=0) & models.Q(quantity__gt=0),
                name="strategy_positive_budget_quantity",
            ),
            models.CheckConstraint(
                condition=models.Q(buy_below__gt=0)
                & models.Q(sell_at_or_above__gt=models.F("buy_below")),
                name="strategy_valid_price_thresholds",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.share.ticker})"


class SimulatedTrade(models.Model):
    class Side(models.TextChoices):
        BUY = "buy", "Покупка"
        SELL = "sell", "Продажа"

    strategy = models.ForeignKey(
        InvestmentStrategy, on_delete=models.CASCADE, related_name="trades"
    )
    date = models.DateField()
    side = models.CharField(max_length=4, choices=Side.choices)
    price = models.DecimalField(max_digits=20, decimal_places=9)
    quantity = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=20, decimal_places=2)

    class Meta:
        ordering = ("date", "id")
        verbose_name = "Виртуальная операция"
        verbose_name_plural = "Виртуальные операции"
        constraints = [
            models.UniqueConstraint(
                fields=("strategy", "date"),
                name="unique_simulated_strategy_trade_date",
            )
        ]

    def __str__(self):
        return f"{self.get_side_display()} {self.strategy.share.ticker} {self.date}"


class Watchlist(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="watchlists",
    )
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name", "id")
        verbose_name = "Список наблюдения"
        verbose_name_plural = "Списки наблюдения"

    def __str__(self):
        return f"{self.name} ({self.owner})"


class WatchlistEntry(models.Model):
    class Direction(models.TextChoices):
        AT_OR_ABOVE = "above", "Достигла или выше"
        AT_OR_BELOW = "below", "Достигла или ниже"

    watchlist = models.ForeignKey(
        Watchlist, on_delete=models.CASCADE, related_name="entries"
    )
    share = models.ForeignKey(
        Share, on_delete=models.CASCADE, related_name="watchlist_entries"
    )
    direction = models.CharField(max_length=5, choices=Direction.choices)
    target_price = models.DecimalField(max_digits=20, decimal_places=9)
    is_triggered = models.BooleanField(default=False)
    last_checked_price = models.DecimalField(
        max_digits=20, decimal_places=9, null=True, blank=True
    )
    last_checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("share__ticker",)
        verbose_name = "Наблюдаемая акция"
        verbose_name_plural = "Наблюдаемые акции"
        constraints = [
            models.UniqueConstraint(
                fields=("watchlist", "share"), name="unique_watchlist_share"
            ),
            models.CheckConstraint(
                condition=models.Q(target_price__gt=0),
                name="watchlist_target_price_positive",
            ),
        ]

    def __str__(self):
        return f"{self.share.ticker} {self.get_direction_display()} {self.target_price}"


class PriceNotification(models.Model):
    entry = models.ForeignKey(
        WatchlistEntry, on_delete=models.CASCADE, related_name="notifications"
    )
    triggered_price = models.DecimalField(max_digits=20, decimal_places=9)
    triggered_at = models.DateTimeField()
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ("-triggered_at", "-id")
        verbose_name = "Уведомление о цене"
        verbose_name_plural = "Уведомления о цене"

    def __str__(self):
        return self.message


class InvestmentPortfolio(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="investment_portfolios",
    )
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")
        verbose_name = "Инвестиционный портфель"
        verbose_name_plural = "Инвестиционные портфели"

    def __str__(self):
        return f"{self.name} ({self.owner})"


class PortfolioPosition(models.Model):
    portfolio = models.ForeignKey(
        InvestmentPortfolio, on_delete=models.CASCADE, related_name="positions"
    )
    share = models.ForeignKey(
        Share, on_delete=models.PROTECT, related_name="portfolio_positions"
    )
    quantity = models.DecimalField(max_digits=20, decimal_places=9, default=0)
    average_cost = models.DecimalField(max_digits=20, decimal_places=9, default=0)
    realized_profit = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("share__ticker",)
        verbose_name = "Позиция портфеля"
        verbose_name_plural = "Позиции портфеля"
        constraints = [
            models.UniqueConstraint(
                fields=("portfolio", "share"), name="unique_portfolio_share"
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=0),
                name="portfolio_position_nonnegative_quantity",
            ),
        ]

    def __str__(self):
        return f"{self.portfolio.name}: {self.share.ticker} ({self.quantity})"


class PortfolioTransaction(models.Model):
    class Side(models.TextChoices):
        BUY = "buy", "Покупка"
        SELL = "sell", "Продажа"

    portfolio = models.ForeignKey(
        InvestmentPortfolio, on_delete=models.CASCADE, related_name="transactions"
    )
    share = models.ForeignKey(
        Share, on_delete=models.PROTECT, related_name="portfolio_transactions"
    )
    side = models.CharField(max_length=4, choices=Side.choices)
    quantity = models.DecimalField(max_digits=20, decimal_places=9)
    price = models.DecimalField(max_digits=20, decimal_places=9)
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    realized_profit = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    executed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-executed_at", "-id")
        verbose_name = "Операция портфеля"
        verbose_name_plural = "Операции портфеля"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="portfolio_transaction_positive_quantity",
            ),
            models.CheckConstraint(
                condition=models.Q(price__gt=0),
                name="portfolio_transaction_positive_price",
            ),
        ]

    def __str__(self):
        return f"{self.get_side_display()} {self.share.ticker} x {self.quantity}"
