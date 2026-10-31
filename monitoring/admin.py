from django.contrib import admin

from monitoring.models import Notification, Watchlist


@admin.register(Watchlist)
class WatchlistAdmin(admin.ModelAdmin):
    list_display = ("name", "owner")
    list_select_related = ("owner",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("owner", "share", "direction", "target_price", "price", "created_at")
    list_select_related = ("owner", "share")
