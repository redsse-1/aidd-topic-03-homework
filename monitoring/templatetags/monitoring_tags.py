from django import template

from monitoring.models import Watchlist

register = template.Library()


@register.inclusion_tag("monitoring/watch_form.html", takes_context=True)
def watch_form(context, share):
    """Форма добавления акции в список наблюдения для страницы акции"""
    user = context["user"]
    watchlists = Watchlist.objects.filter(owner=user) if user.is_authenticated else None
    return {
        "share": share,
        "watchlists": watchlists,
        "show": user.is_authenticated,
        "csrf_token": context.get("csrf_token"),
    }
