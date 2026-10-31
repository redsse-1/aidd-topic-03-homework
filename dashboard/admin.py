from django.contrib import admin

from dashboard.models import PriceRecord, Share


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


@admin.register(PriceRecord)
class PriceRecordAdmin(admin.ModelAdmin):
    list_display = ("share", "kind", "recorded_at", "price")
    list_filter = ("kind",)
    search_fields = ("share__ticker",)
    list_select_related = ("share",)
