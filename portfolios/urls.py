from django.urls import path

from portfolios import views

app_name = "portfolios"

urlpatterns = [
    path("", views.PortfolioListView.as_view(), name="list"),
    path("create/", views.PortfolioCreateView.as_view(), name="create"),
    path("<int:pk>/", views.PortfolioDetailView.as_view(), name="detail"),
    path("<int:pk>/update/", views.PortfolioUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", views.PortfolioDeleteView.as_view(), name="delete"),
    path("<int:pk>/trade/", views.OperationView.as_view(), name="trade"),
    path("<int:pk>/history/", views.OperationHistoryView.as_view(), name="history"),
]
