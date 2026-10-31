from django import forms
from django.core.exceptions import ValidationError

from dashboard.models import Share

from .conditions import BuyCondition, SellCondition
from .models import Strategy


class StrategyForm(forms.ModelForm):
    """Стратегия. Владелец задаётся в представлении, а не в форме."""

    share = forms.ModelChoiceField(
        queryset=Share.objects.order_by("ticker"), label="Акция"
    )

    class Meta:
        model = Strategy
        exclude = ("owner", "created_at")
        widgets = {
            "date_from": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "date_to": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def clean(self):
        cleaned_data = super().clean()

        buy = cleaned_data.get("buy_condition")
        sell = cleaned_data.get("sell_condition")
        if buy and buy != BuyCondition.SMA_CROSS_UP and not cleaned_data.get("buy_value"):
            self.add_error("buy_value", "Для этого условия нужно значение")
        if sell and sell != SellCondition.SMA_CROSS_DOWN and not cleaned_data.get("sell_value"):
            self.add_error("sell_value", "Для этого условия нужно значение")

        short = cleaned_data.get("sma_short")
        long = cleaned_data.get("sma_long")
        if short and long and short >= long:
            self.add_error("sma_short", "Короткая средняя должна быть меньше длинной")

        date_from = cleaned_data.get("date_from")
        date_to = cleaned_data.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise ValidationError("Начало моделирования позже конца")
        return cleaned_data
