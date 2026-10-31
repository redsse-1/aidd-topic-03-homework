import uuid

from django.db import models


def generate_uid():
    return str(uuid.uuid4())


class Share(models.Model):
    """Акция"""

    figi = models.CharField(max_length=255, unique=True)
    isin = models.CharField(max_length=255)
    name = models.CharField(max_length=255, verbose_name="Наименование компании")
    ticker = models.CharField(max_length=32, unique=True, verbose_name="Тикер")
    currency = models.CharField(max_length=20, verbose_name="Валюта")
    uid = models.CharField(max_length=255, unique=True, default=generate_uid)
    last_price = models.FloatField(blank=True, null=True, verbose_name="Текущая цена")
    is_trend_high = models.BooleanField(
        blank=True, null=True, verbose_name="Растет цена"
    )
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)

    class Meta:
        verbose_name = "Акция"
        verbose_name_plural = "Акции"

    def __str__(self):
        return f"{self.ticker} {self.name}"


class PriceRecord(models.Model):
    """Запись истории цены акции"""

    class Kind(models.TextChoices):
        DAILY = "daily", "Дневное закрытие"
        QUOTE = "quote", "Внутридневная котировка"

    share = models.ForeignKey(
        Share, on_delete=models.CASCADE, related_name="price_records"
    )
    kind = models.CharField(max_length=5, choices=Kind.choices)
    recorded_at = models.DateTimeField(verbose_name="Время цены в источнике")
    price = models.FloatField(verbose_name="Цена")

    class Meta:
        verbose_name = "Запись истории цены"
        verbose_name_plural = "История цен"
        constraints = [
            models.UniqueConstraint(
                fields=["share", "kind", "recorded_at"],
                name="unique_price_record",
            )
        ]
        indexes = [models.Index(fields=["kind", "recorded_at"])]

    def __str__(self):
        return f"{self.share_id} {self.kind} {self.recorded_at}: {self.price}"
