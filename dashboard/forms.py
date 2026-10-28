from django import forms

from .models import InvestmentStrategy, Share, Watchlist, WatchlistEntry


class PriceHistoryPeriodForm(forms.Form):
    period = forms.ChoiceField(
        label="Период",
        choices=(
            ("7", "7 дней"),
            ("30", "30 дней"),
            ("90", "90 дней"),
            ("180", "180 дней"),
            ("365", "1 год"),
            ("all", "Вся история"),
        ),
    )


class ShareModelForm(forms.ModelForm):
    """Инструмент"""

    class Meta:
        model = Share
        fields = "__all__"


class InvestmentStrategyForm(forms.ModelForm):
    class Meta:
        model = InvestmentStrategy
        fields = (
            "name",
            "share",
            "initial_cash",
            "quantity",
            "buy_below",
            "sell_at_or_above",
        )
        widgets = {
            "share": forms.Select(attrs={"class": "form-control"}),
            "initial_cash": forms.NumberInput(
                attrs={"class": "form-control", "min": "0.01", "step": "0.01"}
            ),
            "quantity": forms.NumberInput(
                attrs={"class": "form-control", "min": "1", "step": "1"}
            ),
            "buy_below": forms.NumberInput(
                attrs={"class": "form-control", "min": "0.000000001", "step": "any"}
            ),
            "sell_at_or_above": forms.NumberInput(
                attrs={"class": "form-control", "min": "0.000000001", "step": "any"}
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        initial_cash = cleaned_data.get("initial_cash")
        buy_below = cleaned_data.get("buy_below")
        sell_at_or_above = cleaned_data.get("sell_at_or_above")
        if initial_cash is not None and initial_cash <= 0:
            self.add_error("initial_cash", "Начальный капитал должен быть больше нуля.")
        if buy_below is not None and buy_below <= 0:
            self.add_error("buy_below", "Цена покупки должна быть больше нуля.")
        if sell_at_or_above is not None and sell_at_or_above <= 0:
            self.add_error(
                "sell_at_or_above", "Цена продажи должна быть больше нуля."
            )
        if (
            buy_below is not None
            and sell_at_or_above is not None
            and sell_at_or_above <= buy_below
        ):
            self.add_error(
                "sell_at_or_above",
                "Цена продажи должна быть выше цены покупки.",
            )
        return cleaned_data


class WatchlistForm(forms.ModelForm):
    class Meta:
        model = Watchlist
        fields = ("name",)
        widgets = {"name": forms.TextInput(attrs={"class": "form-control"})}


class WatchlistEntryForm(forms.ModelForm):
    class Meta:
        model = WatchlistEntry
        fields = ("share", "direction", "target_price")
        widgets = {
            "share": forms.Select(attrs={"class": "form-control"}),
            "direction": forms.Select(attrs={"class": "form-control"}),
            "target_price": forms.NumberInput(
                attrs={"class": "form-control", "min": "0.000000001", "step": "any"}
            ),
        }

    def clean_target_price(self):
        target_price = self.cleaned_data["target_price"]
        if target_price <= 0:
            raise forms.ValidationError("Целевой уровень должен быть больше нуля.")
        return target_price


class WatchlistEntryTargetForm(forms.ModelForm):
    class Meta:
        model = WatchlistEntry
        fields = ("direction", "target_price")
        widgets = {
            "direction": forms.Select(attrs={"class": "form-control"}),
            "target_price": forms.NumberInput(
                attrs={"class": "form-control", "min": "0.000000001", "step": "any"}
            ),
        }

    def clean_target_price(self):
        target_price = self.cleaned_data["target_price"]
        if target_price <= 0:
            raise forms.ValidationError("Целевой уровень должен быть больше нуля.")
        return target_price
