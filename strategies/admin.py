from django.contrib import admin

from strategies.models import Strategy


@admin.register(Strategy)
class StrategyAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "share", "buy_condition", "sell_condition")
    list_select_related = ("owner", "share")
    search_fields = ("name", "share__ticker")
