from django.contrib import admin

from portfolios.models import Portfolio


@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ("name", "owner")
    list_select_related = ("owner",)
