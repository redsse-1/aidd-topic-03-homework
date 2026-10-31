from django.db import models


class BuyCondition(models.TextChoices):
    PRICE_BELOW = "price_below", "Цена закрытия не выше значения"
    DROP_FROM_HIGH = "drop_from_high", "Падение от максимума за период, %"
    SMA_CROSS_UP = "sma_cross_up", "Короткая средняя пересекла длинную снизу вверх"


class SellCondition(models.TextChoices):
    PRICE_ABOVE = "price_above", "Цена закрытия не ниже значения"
    TAKE_PROFIT = "take_profit", "Рост от цены покупки, %"
    SMA_CROSS_DOWN = "sma_cross_down", "Короткая средняя пересекла длинную сверху вниз"
