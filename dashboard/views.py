from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, View, UpdateView

from .forms import DEFAULT_PERIOD, PERIOD_CHOICES, PeriodForm, ShareModelForm
from .models import Share
from .services.graph import get_graph
from .services.price_history import compute_stats, daily_changes, get_series
from django.contrib.auth.mixins import UserPassesTestMixin


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
    @staticmethod
    def get(request, pk):
        share = get_object_or_404(Share, id=pk)
        form = PeriodForm(request.GET)
        points = []
        selected_period = None
        if form.is_valid():
            points = get_series(share, *form.get_range())
            if not form.is_custom():
                selected_period = form.cleaned_data["period"] or DEFAULT_PERIOD

        return render(
            request,
            "dashboard/detail.html",
            {
                "share": share,
                "form": form,
                "periods": PERIOD_CHOICES,
                "selected_period": selected_period,
                "plot_div": get_graph(share, points),
                "stats": compute_stats(points),
                "changes": daily_changes(points),
            },
        )


class ShareCreateView(IsUserAuthenticatedMixin, CreateView):
    """Добавление инструмента"""

    template_name = "dashboard/create.html"
    form_class = ShareModelForm
    success_url = reverse_lazy("dashboard:index")


class ShareUpdateView(IsUserAuthenticatedMixin, UpdateView):
    """Редактирование инструмента"""

    model = Share
    template_name = "dashboard/create.html"
    form_class = ShareModelForm
    success_url = reverse_lazy("dashboard:index")


class ShareDeleteView(IsUserAuthenticatedMixin, DeleteView):
    """Удаление инструмента"""

    model = Share
    template_name = "dashboard/delete.html"
    success_url = reverse_lazy("dashboard:index")
