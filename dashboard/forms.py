from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Share

PERIODS = (
    ("1w", "Неделя", 7),
    ("1m", "Месяц", 30),
    ("3m", "3 месяца", 90),
    ("6m", "6 месяцев", 180),
    ("1y", "Год", 365),
    ("all", "Всё время", None),
)
PERIOD_CHOICES = [(value, label) for value, label, _ in PERIODS]
PERIOD_DAYS = {value: days for value, _, days in PERIODS}
DEFAULT_PERIOD = "6m"


class ShareModelForm(forms.ModelForm):
    """Инструмент"""

    class Meta:
        model = Share
        fields = "__all__"


class PeriodForm(forms.Form):
    """Период истории цен: готовый вариант или свой диапазон дат"""

    period = forms.ChoiceField(choices=PERIOD_CHOICES, required=False, label="Период")
    date_from = forms.DateField(required=False, label="С даты")
    date_to = forms.DateField(required=False, label="По дату")

    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get("date_from")
        date_to = cleaned_data.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise ValidationError("Начальная дата позже конечной")
        return cleaned_data

    def is_custom(self):
        data = self.cleaned_data
        return bool(data.get("date_from") or data.get("date_to"))

    def get_range(self):
        """Вернуть (начало, конец). Начало None означает всю историю."""
        today = timezone.localdate()
        if self.is_custom():
            return self.cleaned_data["date_from"], self.cleaned_data["date_to"] or today
        days = PERIOD_DAYS[self.cleaned_data.get("period") or DEFAULT_PERIOD]
        return (today - timedelta(days=days) if days else None), today
