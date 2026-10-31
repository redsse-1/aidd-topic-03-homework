from django.urls import path

from strategies.views import (
    StrategyCreateView,
    StrategyDeleteView,
    StrategyDetailView,
    StrategyListView,
    StrategyRunView,
    StrategyUpdateView,
)

app_name = "strategies"

urlpatterns = [
    path("", StrategyListView.as_view(), name="list"),
    path("create/", StrategyCreateView.as_view(), name="create"),
    path("<int:pk>/", StrategyDetailView.as_view(), name="detail"),
    path("<int:pk>/update/", StrategyUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", StrategyDeleteView.as_view(), name="delete"),
    path("<int:pk>/run/", StrategyRunView.as_view(), name="run"),
]
