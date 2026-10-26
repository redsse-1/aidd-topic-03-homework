from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    View,
    UpdateView,
)

from .forms import InvestmentStrategyForm, PriceHistoryPeriodForm, ShareModelForm
from .models import InvestmentStrategy, Share
from .services.graph import get_graph
from .services.strategy_simulator import NoPriceHistoryError, run_strategy

MOSCOW = ZoneInfo("Europe/Moscow")


class IsUserAuthenticatedMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated

    @staticmethod
    def handle_no_permission():
        return redirect("dashboard:index")


class ShareListView(ListView):
    """Список акций"""

    model = Share
    template_name = "dashboard/list.html"
    paginate_by = 100
    ordering = ["name"]


class ShareDetailView(View):
    def get(self, request, pk):
        share = get_object_or_404(Share, id=pk)
        form = PriceHistoryPeriodForm(
            request.GET if request.GET else None,
            initial={"period": "180"},
        )
        if request.GET and not form.is_valid():
            return render(
                request,
                "dashboard/detail.html",
                {"share": share, "history_form": form},
                status=400,
            )

        period = form.cleaned_data["period"] if form.is_bound else "180"
        history = share.price_history.all()
        if period != "all":
            end_date = timezone.localdate(timezone.now(), timezone=MOSCOW)
            start_date = end_date - timedelta(days=int(period) - 1)
            history = history.filter(date__gte=start_date, date__lte=end_date)
        history = list(history.order_by("date"))

        absolute_change = percentage_change = None
        if history:
            absolute_change = history[-1].close - history[0].close
            if history[0].close != Decimal("0"):
                percentage_change = (
                    absolute_change / history[0].close * Decimal("100")
                )

        return render(
            request,
            "dashboard/detail.html",
            {
                "plot_div": get_graph(share, history),
                "share": share,
                "history_form": form,
                "history_count": len(history),
                "first_price": history[0] if history else None,
                "last_price": history[-1] if history else None,
                "absolute_change": absolute_change,
                "percentage_change": percentage_change,
            },
        )


class ShareCreateView(IsUserAuthenticatedMixin, CreateView):
    """Добавление инструмента"""

    template_name = "dashboard/create.html"
    form_class = ShareModelForm
    success_url = reverse_lazy("dashboard:index")


class StrategyListView(LoginRequiredMixin, ListView):
    model = InvestmentStrategy
    template_name = "dashboard/strategies/list.html"
    context_object_name = "strategies"

    def get_queryset(self):
        return (
            InvestmentStrategy.objects.filter(owner=self.request.user)
            .select_related("share")
        )


class StrategyCreateView(LoginRequiredMixin, CreateView):
    model = InvestmentStrategy
    form_class = InvestmentStrategyForm
    template_name = "dashboard/strategies/form.html"

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("dashboard:strategy-detail", args=[self.object.pk])


class StrategyUpdateView(LoginRequiredMixin, UpdateView):
    model = InvestmentStrategy
    form_class = InvestmentStrategyForm
    template_name = "dashboard/strategies/form.html"

    def get_queryset(self):
        return InvestmentStrategy.objects.filter(owner=self.request.user)

    def get_success_url(self):
        return reverse("dashboard:strategy-detail", args=[self.object.pk])


class StrategyDetailView(LoginRequiredMixin, DetailView):
    model = InvestmentStrategy
    template_name = "dashboard/strategies/detail.html"
    context_object_name = "strategy"

    def get_queryset(self):
        return (
            InvestmentStrategy.objects.filter(owner=self.request.user)
            .select_related("share")
        )


class StrategyRunView(LoginRequiredMixin, View):
    def post(self, request, pk):
        strategy = get_object_or_404(InvestmentStrategy, pk=pk, owner=request.user)
        try:
            run_strategy(strategy.pk)
        except NoPriceHistoryError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, "Симуляция завершена по накопленной истории цен.")
        return redirect("dashboard:strategy-detail", pk=strategy.pk)


class ShareUpdateView(IsUserAuthenticatedMixin, UpdateView):
    """Редактирование инструмента"""

    model = Share
    template_name = "dashboard/create.html"
    form_class = ShareModelForm
    success_url = reverse_lazy("dashboard:index")


class ShareDeleteView(IsUserAuthenticatedMixin, DeleteView):
    """Удаление задачи"""

    model = Share
    template_name = "dashboard/delete.html"
    success_url = reverse_lazy("dashboard:index")
