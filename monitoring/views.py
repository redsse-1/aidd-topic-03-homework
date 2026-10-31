from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
    View,
)

from dashboard.views import IsUserAuthenticatedMixin

from .forms import PriceTargetForm, WatchlistForm, WatchlistItemForm
from .models import Notification, PriceTarget, Watchlist, WatchlistItem

# Единственные источники данных для представлений: только записи пользователя


def user_watchlists(user):
    return Watchlist.objects.filter(owner=user)


def user_items(user):
    return WatchlistItem.objects.filter(watchlist__owner=user).select_related(
        "watchlist", "share"
    )


def user_targets(user):
    return PriceTarget.objects.filter(item__watchlist__owner=user).select_related(
        "item__watchlist", "item__share"
    )


def user_notifications(user):
    return Notification.objects.filter(owner=user)


class WatchlistListView(IsUserAuthenticatedMixin, ListView):
    """Списки наблюдения пользователя"""

    template_name = "monitoring/list.html"
    context_object_name = "watchlists"

    def get_queryset(self):
        return user_watchlists(self.request.user).annotate(shares=Count("items"))


class OwnerFormMixin:
    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "owner": self.request.user}

    def get_success_url(self):
        return reverse("monitoring:detail", args=[self.object.pk])


class WatchlistCreateView(IsUserAuthenticatedMixin, OwnerFormMixin, CreateView):
    """Создание списка"""

    template_name = "monitoring/form.html"
    form_class = WatchlistForm
    extra_context = {"title": "Новый список наблюдения"}

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class WatchlistUpdateView(IsUserAuthenticatedMixin, OwnerFormMixin, UpdateView):
    """Переименование списка"""

    template_name = "monitoring/form.html"
    form_class = WatchlistForm
    extra_context = {"title": "Название списка"}

    def get_queryset(self):
        return user_watchlists(self.request.user)


class WatchlistDeleteView(IsUserAuthenticatedMixin, DeleteView):
    """Удаление списка"""

    template_name = "monitoring/delete.html"
    success_url = reverse_lazy("monitoring:list")
    extra_context = {"title": "Удаление списка"}

    def get_queryset(self):
        return user_watchlists(self.request.user)


class WatchlistDetailView(IsUserAuthenticatedMixin, DetailView):
    """Акции списка и их целевые уровни"""

    template_name = "monitoring/detail.html"
    context_object_name = "watchlist"

    def get_queryset(self):
        return user_watchlists(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["items"] = self.object.items.select_related("share").prefetch_related(
            "targets"
        )
        context["form"] = WatchlistItemForm(
            owner=self.request.user, initial={"watchlist": self.object}
        )
        return context


class WatchlistItemAddView(IsUserAuthenticatedMixin, View):
    """Добавление акции в список: со страницы списка и со страницы акции"""

    def post(self, request):
        form = WatchlistItemForm(request.POST, owner=request.user)
        if form.is_valid():
            item = WatchlistItem.objects.create(
                watchlist=form.cleaned_data["watchlist"],
                share=form.cleaned_data["share"],
            )
            return redirect("monitoring:detail", pk=item.watchlist_id)

        for errors in form.errors.values():
            messages.error(request, errors[0])
        watchlist = form.cleaned_data.get("watchlist")
        if watchlist:
            return redirect("monitoring:detail", pk=watchlist.pk)
        return redirect("monitoring:list")


class WatchlistItemDeleteView(IsUserAuthenticatedMixin, View):
    """Удаление акции из списка вместе с её уровнями"""

    def post(self, request, pk):
        item = get_object_or_404(user_items(request.user), pk=pk)
        watchlist_id = item.watchlist_id
        item.delete()
        return redirect("monitoring:detail", pk=watchlist_id)


class TargetFormMixin:
    template_name = "monitoring/form.html"
    form_class = PriceTargetForm

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "item": self.get_item()}

    def get_context_data(self, **kwargs):
        share = self.get_item().share
        price = share.last_price
        return super().get_context_data(
            title=f"Целевой уровень: {share.ticker}",
            hint=f"Текущая цена: {price} {share.currency}" if price else None,
            **kwargs,
        )

    def get_success_url(self):
        return reverse("monitoring:detail", args=[self.get_item().watchlist_id])


class PriceTargetCreateView(IsUserAuthenticatedMixin, TargetFormMixin, CreateView):
    """Задание целевого уровня"""

    def get_item(self):
        return get_object_or_404(user_items(self.request.user), pk=self.kwargs["pk"])

    def form_valid(self, form):
        form.instance.item = self.get_item()
        return super().form_valid(form)


class PriceTargetUpdateView(IsUserAuthenticatedMixin, TargetFormMixin, UpdateView):
    """Изменение целевого уровня. Изменённый уровень отслеживается заново."""

    def get_queryset(self):
        return user_targets(self.request.user)

    def get_item(self):
        return self.get_object().item

    def form_valid(self, form):
        if form.has_changed():
            form.instance.is_triggered = False
        return super().form_valid(form)


class PriceTargetDeleteView(IsUserAuthenticatedMixin, View):
    """Удаление целевого уровня. Прежние уведомления сохраняются."""

    def post(self, request, pk):
        target = get_object_or_404(user_targets(request.user), pk=pk)
        watchlist_id = target.item.watchlist_id
        target.delete()
        return redirect("monitoring:detail", pk=watchlist_id)


class NotificationListView(IsUserAuthenticatedMixin, ListView):
    """Уведомления пользователя"""

    template_name = "monitoring/notifications.html"
    context_object_name = "notifications"
    paginate_by = 50

    def get_queryset(self):
        return user_notifications(self.request.user).select_related("share")


class NotificationReadView(IsUserAuthenticatedMixin, View):
    """Отметка уведомления прочитанным"""

    def post(self, request, pk):
        notification = get_object_or_404(user_notifications(request.user), pk=pk)
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])
        return redirect("monitoring:notifications")


class NotificationReadAllView(IsUserAuthenticatedMixin, View):
    """Отметка всех уведомлений прочитанными"""

    def post(self, request):
        user_notifications(request.user).filter(read_at__isnull=True).update(
            read_at=timezone.now()
        )
        return redirect("monitoring:notifications")
