from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    ListView,
    UpdateView,
    View,
)

from dashboard.views import IsUserAuthenticatedMixin

from .forms import OperationForm, PortfolioForm
from .models import Portfolio
from .services import OperationError, execute_operation, summarize


def user_portfolios(user):
    """Единственный источник портфелей для представлений: только свои"""
    return Portfolio.objects.filter(owner=user)


def portfolio_positions(portfolio):
    return list(portfolio.positions.select_related("share"))


class OwnPortfolioMixin(IsUserAuthenticatedMixin):
    def get_queryset(self):
        return user_portfolios(self.request.user)


class PortfolioListView(OwnPortfolioMixin, ListView):
    """Портфели пользователя с оценкой"""

    template_name = "portfolios/list.html"
    context_object_name = "portfolios"

    def get_queryset(self):
        return super().get_queryset().prefetch_related("positions__share")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["rows"] = [
            (portfolio, summarize(list(portfolio.positions.all())))
            for portfolio in context["portfolios"]
        ]
        return context


class PortfolioFormMixin:
    template_name = "portfolios/form.html"
    form_class = PortfolioForm

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "owner": self.request.user}

    def get_success_url(self):
        return reverse("portfolios:detail", args=[self.object.pk])


class PortfolioCreateView(IsUserAuthenticatedMixin, PortfolioFormMixin, CreateView):
    """Создание портфеля"""

    extra_context = {"title": "Новый портфель"}

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class PortfolioUpdateView(OwnPortfolioMixin, PortfolioFormMixin, UpdateView):
    """Переименование портфеля"""

    extra_context = {"title": "Название портфеля"}


class PortfolioDeleteView(OwnPortfolioMixin, DeleteView):
    """Удаление портфеля вместе с позициями и историей"""

    template_name = "portfolios/delete.html"
    context_object_name = "portfolio"
    success_url = reverse_lazy("portfolios:list")


class PortfolioDetailView(IsUserAuthenticatedMixin, View):
    """Позиции, стоимость и прибыль портфеля"""

    def get(self, request, pk):
        portfolio = get_object_or_404(user_portfolios(request.user), pk=pk)
        return render(
            request,
            "portfolios/detail.html",
            {
                "portfolio": portfolio,
                "summary": summarize(portfolio_positions(portfolio)),
            },
        )


class OperationView(IsUserAuthenticatedMixin, View):
    """Форма покупки и продажи"""

    template_name = "portfolios/operation.html"

    def get_portfolio(self, pk):
        return get_object_or_404(user_portfolios(self.request.user), pk=pk)

    def render_form(self, portfolio, form):
        return render(
            self.request, self.template_name, {"portfolio": portfolio, "form": form}
        )

    def get(self, request, pk):
        initial = {
            "share": request.GET.get("share"),
            "side": request.GET.get("side", "buy"),
        }
        return self.render_form(self.get_portfolio(pk), OperationForm(initial=initial))

    def post(self, request, pk):
        portfolio = self.get_portfolio(pk)
        form = OperationForm(request.POST)
        if form.is_valid():
            try:
                execute_operation(
                    portfolio,
                    form.cleaned_data["share"],
                    form.cleaned_data["side"],
                    form.cleaned_data["quantity"],
                )
            except OperationError as e:
                form.add_error(None, str(e))
            else:
                return redirect("portfolios:detail", pk=portfolio.pk)
        return self.render_form(portfolio, form)


class OperationHistoryView(IsUserAuthenticatedMixin, ListView):
    """История операций портфеля"""

    template_name = "portfolios/history.html"
    context_object_name = "operations"
    paginate_by = 50

    def get_portfolio(self):
        return get_object_or_404(user_portfolios(self.request.user), pk=self.kwargs["pk"])

    def get_queryset(self):
        return self.get_portfolio().operations.select_related("share")

    def get_context_data(self, **kwargs):
        return super().get_context_data(portfolio=self.get_portfolio(), **kwargs)
