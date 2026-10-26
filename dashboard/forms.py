from django import forms

from .models import Share


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
