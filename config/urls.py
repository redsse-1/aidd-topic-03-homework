from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("dashboard.urls")),
    path("user/", include("user.urls")),
    path("strategies/", include("strategies.urls")),
    path("monitoring/", include("monitoring.urls")),
    path("portfolios/", include("portfolios.urls")),
]
