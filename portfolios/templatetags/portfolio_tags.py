from django import template

from portfolios.models import Portfolio

register = template.Library()


@register.inclusion_tag("portfolios/trade_links.html", takes_context=True)
def trade_links(context, share):
    """Ссылки на покупку акции в портфели пользователя для страницы акции"""
    user = context["user"]
    portfolios = Portfolio.objects.filter(owner=user) if user.is_authenticated else None
    return {"share": share, "portfolios": portfolios}
