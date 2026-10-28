from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import IntegrityError, transaction
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

from .forms import (
    InvestmentStrategyForm,
    PriceHistoryPeriodForm,
    ShareModelForm,
    WatchlistEntryForm,
    WatchlistEntryTargetForm,
    WatchlistForm,
)
from .models import (
    InvestmentStrategy,
    PriceNotification,
    Share,
    Watchlist,
    WatchlistEntry,
)
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


class WatchlistListView(LoginRequiredMixin, ListView):
    model = Watchlist
    template_name = "dashboard/watchlists/list.html"
    context_object_name = "watchlists"

    def get_queryset(self):
        return Watchlist.objects.filter(owner=self.request.user).prefetch_related(
            "entries"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("form", WatchlistForm())
        return context

    def post(self, request, *args, **kwargs):
        form = WatchlistForm(request.POST)
        if form.is_valid():
            watchlist = form.save(commit=False)
            watchlist.owner = request.user
            watchlist.save()
            return redirect("dashboard:watchlist-detail", pk=watchlist.pk)
        self.object_list = self.get_queryset()
        return self.render_to_response(self.get_context_data(form=form))


class WatchlistDetailView(LoginRequiredMixin, DetailView):
    model = Watchlist
    template_name = "dashboard/watchlists/detail.html"
    context_object_name = "watchlist"

    def get_queryset(self):
        return Watchlist.objects.filter(owner=self.request.user).prefetch_related(
            "entries__share"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("entry_form", WatchlistEntryForm())
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = WatchlistEntryForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.watchlist = self.object
            if WatchlistEntry.objects.filter(
                watchlist=self.object, share=entry.share
            ).exists():
                form.add_error("share", "Эта акция уже есть в списке наблюдения.")
            else:
                try:
                    with transaction.atomic():
                        entry.save()
                except IntegrityError:
                    form.add_error(
                        "share", "Эта акция уже есть в списке наблюдения."
                    )
                else:
                    messages.success(request, "Акция добавлена в список наблюдения.")
                    return redirect("dashboard:watchlist-detail", pk=self.object.pk)
        return self.render_to_response(self.get_context_data(entry_form=form))


class WatchlistEntryDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        entry = get_object_or_404(
            WatchlistEntry,
            pk=pk,
            watchlist__owner=request.user,
        )
        watchlist_id = entry.watchlist_id
        entry.delete()
        return redirect("dashboard:watchlist-detail", pk=watchlist_id)


class WatchlistDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        watchlist = get_object_or_404(Watchlist, pk=pk, owner=request.user)
        watchlist.delete()
        return redirect("dashboard:watchlist-list")


class WatchlistEntryUpdateView(LoginRequiredMixin, UpdateView):
    model = WatchlistEntry
    form_class = WatchlistEntryTargetForm
    template_name = "dashboard/watchlists/entry_form.html"
    http_method_names = ("get", "post", "head", "options")

    def get_queryset(self):
        return WatchlistEntry.objects.filter(watchlist__owner=self.request.user)

    def form_valid(self, form):
        if {"direction", "target_price"} & set(form.changed_data):
            form.instance.is_triggered = False
            form.instance.last_checked_price = None
            form.instance.last_checked_at = None
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("dashboard:watchlist-detail", args=[self.object.watchlist_id])


class PriceNotificationListView(LoginRequiredMixin, ListView):
    model = PriceNotification
    template_name = "dashboard/watchlists/notifications.html"
    context_object_name = "notifications"
    paginate_by = 50

    def get_queryset(self):
        return PriceNotification.objects.filter(
            entry__watchlist__owner=self.request.user
        ).select_related("entry__share", "entry__watchlist")


class PriceNotificationReadView(LoginRequiredMixin, View):
    def post(self, request, pk):
        notification = get_object_or_404(
            PriceNotification,
            pk=pk,
            entry__watchlist__owner=request.user,
        )
        notification.is_read = True
        notification.save(update_fields=("is_read",))
        return redirect("dashboard:notifications")


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
