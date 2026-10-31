from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView, View

from dashboard.views import IsUserAuthenticatedMixin

from .charts import equity_chart, price_chart
from .engine import SimulationError
from .forms import StrategyForm
from .models import SimulationResult, Strategy
from .services import load_closes, run_simulation

# Изменение этих полей не влияет на результат расчёта
NOT_AFFECTING_RESULT = {"name", "auto_update"}


def user_strategies(user):
    """Единственный источник стратегий для представлений: только свои"""
    return Strategy.objects.filter(owner=user).select_related("share")


class OwnStrategyMixin(IsUserAuthenticatedMixin):
    def get_queryset(self):
        return user_strategies(self.request.user)


class StrategyListView(OwnStrategyMixin, ListView):
    """Список стратегий пользователя"""

    template_name = "strategies/list.html"
    context_object_name = "strategies"

    def get_queryset(self):
        return super().get_queryset().select_related("result")


class StrategyCreateView(IsUserAuthenticatedMixin, CreateView):
    """Создание стратегии"""

    template_name = "strategies/form.html"
    form_class = StrategyForm

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("strategies:detail", args=[self.object.pk])


class StrategyUpdateView(OwnStrategyMixin, UpdateView):
    """Редактирование стратегии"""

    template_name = "strategies/form.html"
    form_class = StrategyForm

    def form_valid(self, form):
        with transaction.atomic():
            if set(form.changed_data) - NOT_AFFECTING_RESULT:
                SimulationResult.objects.filter(strategy=form.instance).delete()
            return super().form_valid(form)

    def get_success_url(self):
        return reverse("strategies:detail", args=[self.object.pk])


class StrategyDeleteView(OwnStrategyMixin, DeleteView):
    """Удаление стратегии"""

    template_name = "strategies/delete.html"
    context_object_name = "strategy"
    success_url = reverse_lazy("strategies:list")


class StrategyDetailView(IsUserAuthenticatedMixin, View):
    """Стратегия: условия, оценка эффективности и журнал операций"""

    def get(self, request, pk):
        strategy = get_object_or_404(user_strategies(request.user), pk=pk)
        context = {"strategy": strategy}

        result = getattr(strategy, "result", None)
        if result:
            trades = list(result.trades.all())
            closes, start = load_closes(strategy)
            context.update(
                result=result,
                trades=trades,
                price_chart=price_chart(closes[start:], trades),
                equity_chart=equity_chart(result.equity),
            )
        return render(request, "strategies/detail.html", context)


class StrategyRunView(IsUserAuthenticatedMixin, View):
    """Запуск моделирования"""

    def post(self, request, pk):
        strategy = get_object_or_404(user_strategies(request.user), pk=pk)
        try:
            run_simulation(strategy)
        except SimulationError as e:
            messages.error(request, str(e))
        return redirect("strategies:detail", pk=pk)
