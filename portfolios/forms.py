from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator

from dashboard.models import Share

from .models import Operation, Portfolio

MAX_QUANTITY = 1_000_000_000


class PortfolioForm(forms.ModelForm):
    """Портфель. Владелец задаётся в представлении."""

    class Meta:
        model = Portfolio
        fields = ("name",)

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner

    def clean_name(self):
        name = self.cleaned_data["name"]
        duplicates = Portfolio.objects.filter(owner=self.owner, name=name)
        if duplicates.exclude(pk=self.instance.pk).exists():
            raise ValidationError("Портфель с таким названием уже есть")
        return name


class ShareChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, share):
        price = share.last_price if share.last_price else "нет цены"
        return f"{share.ticker} — {share.name} ({price})"


class OperationForm(forms.Form):
    """Операция. Цены в форме нет: она берётся из БД в момент исполнения."""

    side = forms.ChoiceField(choices=Operation.Side.choices, label="Операция")
    share = ShareChoiceField(queryset=Share.objects.order_by("ticker"), label="Акция")
    quantity = forms.IntegerField(
        label="Количество, шт.",
        validators=[MinValueValidator(1), MaxValueValidator(MAX_QUANTITY)],
    )
