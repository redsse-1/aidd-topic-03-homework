from django.contrib import admin

from dashboard.models import (
    InvestmentStrategy,
    Share,
    SharePriceHistory,
    SimulatedTrade,
    PriceNotification,
    Watchlist,
    WatchlistEntry,
)


@admin.register(Share)
class ShareAdmin(admin.ModelAdmin):
    list_display = ("figi", "isin", "name", "ticker", "currency")
    search_fields = ("figi", "isin", "name", "ticker")
    fields = (
        "figi",
        "isin",
        "name",
        "ticker",
        "currency",
        "uid",
        "last_price",
        "is_trend_high",
    )


@admin.register(SharePriceHistory)
class SharePriceHistoryAdmin(admin.ModelAdmin):
    list_display = ("share", "date", "close", "updated_at")
    list_filter = ("date",)
    search_fields = ("share__ticker", "share__name")


@admin.register(InvestmentStrategy)
class InvestmentStrategyAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "share", "last_run_at", "return_percent")
    list_filter = ("last_run_at",)
    search_fields = ("name", "owner__email", "share__ticker")


@admin.register(SimulatedTrade)
class SimulatedTradeAdmin(admin.ModelAdmin):
    list_display = ("strategy", "date", "side", "price", "quantity", "amount")
    list_filter = ("side", "date")
    search_fields = (
        "strategy__name",
        "strategy__owner__email",
        "strategy__share__ticker",
    )


@admin.register(Watchlist)
class WatchlistAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "created_at")
    search_fields = ("name", "owner__email")


@admin.register(WatchlistEntry)
class WatchlistEntryAdmin(admin.ModelAdmin):
    list_display = ("watchlist", "share", "direction", "target_price", "is_triggered")
    list_filter = ("direction", "is_triggered")
    search_fields = ("watchlist__name", "watchlist__owner__email", "share__ticker")


@admin.register(PriceNotification)
class PriceNotificationAdmin(admin.ModelAdmin):
    list_display = ("entry", "triggered_price", "triggered_at", "is_read")
    list_filter = ("is_read", "triggered_at")
    search_fields = ("entry__watchlist__owner__email", "entry__share__ticker")
