from django.contrib import admin

from dashboard.models import Share, SharePriceHistory


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
