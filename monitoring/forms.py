from django import forms
from django.core.exceptions import ValidationError

from dashboard.models import Share

from .models import PriceTarget, Watchlist, WatchlistItem


class WatchlistForm(forms.ModelForm):
    """Список наблюдения. Владелец задаётся в представлении."""

    class Meta:
        model = Watchlist
        fields = ("name",)

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner

    def clean_name(self):
        name = self.cleaned_data["name"]
        duplicates = Watchlist.objects.filter(owner=self.owner, name=name)
        if duplicates.exclude(pk=self.instance.pk).exists():
            raise ValidationError("Список с таким названием уже есть")
        return name


class WatchlistItemForm(forms.Form):
    """Добавление акции. Выбрать можно только свой список."""

    watchlist = forms.ModelChoiceField(queryset=Watchlist.objects.none(), label="Список")
    share = forms.ModelChoiceField(
        queryset=Share.objects.order_by("ticker"), label="Акция"
    )

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["watchlist"].queryset = Watchlist.objects.filter(owner=owner)

    def clean(self):
        cleaned_data = super().clean()
        watchlist = cleaned_data.get("watchlist")
        share = cleaned_data.get("share")
        if watchlist and share:
            if WatchlistItem.objects.filter(watchlist=watchlist, share=share).exists():
                raise ValidationError("Эта акция уже есть в списке")
        return cleaned_data


class PriceTargetForm(forms.ModelForm):
    """Целевой уровень акции из списка"""

    class Meta:
        model = PriceTarget
        fields = ("direction", "target_price", "is_active")

    def __init__(self, *args, item, **kwargs):
        super().__init__(*args, **kwargs)
        self.item = item

    def clean(self):
        cleaned_data = super().clean()
        direction = cleaned_data.get("direction")
        target_price = cleaned_data.get("target_price")
        if direction and target_price:
            # Одинаковый уровень в двух списках дал бы два уведомления об одном событии
            duplicates = PriceTarget.objects.filter(
                item__watchlist__owner=self.item.watchlist.owner,
                item__share=self.item.share,
                direction=direction,
                target_price=target_price,
            )
            if duplicates.exclude(pk=self.instance.pk).exists():
                raise ValidationError("Такой уровень для этой акции уже задан")
        return cleaned_data
