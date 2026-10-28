from django.urls import include, path

from dashboard.views import (
    ShareCreateView,
    ShareDeleteView,
    ShareDetailView,
    ShareListView,
    StrategyCreateView,
    StrategyDetailView,
    StrategyListView,
    StrategyRunView,
    StrategyUpdateView,
    ShareUpdateView,
    PriceNotificationListView,
    PriceNotificationReadView,
    WatchlistDetailView,
    WatchlistDeleteView,
    WatchlistEntryDeleteView,
    WatchlistEntryUpdateView,
    WatchlistListView,
)

app_name = "dashboard"

urlpatterns = [
    path("", ShareListView.as_view(), name="index"),
    path("<int:pk>", ShareDetailView.as_view(), name="detail"),
    path("create", ShareCreateView.as_view(), name="create"),
    path("update/<int:pk>", ShareUpdateView.as_view(), name="update"),
    path("delete/<int:pk>", ShareDeleteView.as_view(), name="delete"),
    path("strategies/", StrategyListView.as_view(), name="strategy-list"),
    path("strategies/create/", StrategyCreateView.as_view(), name="strategy-create"),
    path(
        "strategies/<int:pk>/",
        StrategyDetailView.as_view(),
        name="strategy-detail",
    ),
    path(
        "strategies/<int:pk>/edit/",
        StrategyUpdateView.as_view(),
        name="strategy-update",
    ),
    path(
        "strategies/<int:pk>/run/",
        StrategyRunView.as_view(),
        name="strategy-run",
    ),
    path("watchlists/", WatchlistListView.as_view(), name="watchlist-list"),
    path(
        "watchlists/<int:pk>/",
        WatchlistDetailView.as_view(),
        name="watchlist-detail",
    ),
    path(
        "watchlists/<int:pk>/delete/",
        WatchlistDeleteView.as_view(),
        name="watchlist-delete",
    ),
    path(
        "watchlist-entries/<int:pk>/edit/",
        WatchlistEntryUpdateView.as_view(),
        name="watchlist-entry-update",
    ),
    path(
        "watchlist-entries/<int:pk>/delete/",
        WatchlistEntryDeleteView.as_view(),
        name="watchlist-entry-delete",
    ),
    path("notifications/", PriceNotificationListView.as_view(), name="notifications"),
    path(
        "notifications/<int:pk>/read/",
        PriceNotificationReadView.as_view(),
        name="notification-read",
    ),
    path("api/", include("dashboard.api.urls")),
]
