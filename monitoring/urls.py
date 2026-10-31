from django.urls import path

from monitoring import views

app_name = "monitoring"

urlpatterns = [
    path("", views.WatchlistListView.as_view(), name="list"),
    path("create/", views.WatchlistCreateView.as_view(), name="create"),
    path("<int:pk>/", views.WatchlistDetailView.as_view(), name="detail"),
    path("<int:pk>/update/", views.WatchlistUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", views.WatchlistDeleteView.as_view(), name="delete"),
    path("items/add/", views.WatchlistItemAddView.as_view(), name="item_add"),
    path(
        "items/<int:pk>/delete/",
        views.WatchlistItemDeleteView.as_view(),
        name="item_delete",
    ),
    path(
        "items/<int:pk>/targets/add/",
        views.PriceTargetCreateView.as_view(),
        name="target_add",
    ),
    path(
        "targets/<int:pk>/update/",
        views.PriceTargetUpdateView.as_view(),
        name="target_update",
    ),
    path(
        "targets/<int:pk>/delete/",
        views.PriceTargetDeleteView.as_view(),
        name="target_delete",
    ),
    path(
        "notifications/",
        views.NotificationListView.as_view(),
        name="notifications",
    ),
    path(
        "notifications/read-all/",
        views.NotificationReadAllView.as_view(),
        name="notifications_read_all",
    ),
    path(
        "notifications/<int:pk>/read/",
        views.NotificationReadView.as_view(),
        name="notification_read",
    ),
]
