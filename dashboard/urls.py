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
    path("api/", include("dashboard.api.urls")),
]
