from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .base import Candle, InstrumentInfo, MarketDataError, MarketDataProvider, Quote
from .iss import IssProvider
from .tinvest import TinvestProvider

__all__ = (
    "Candle",
    "InstrumentInfo",
    "MarketDataError",
    "MarketDataProvider",
    "Quote",
    "get_provider",
)


def get_provider():
    """Вернуть провайдера, выбранного переменной MARKET_DATA_PROVIDER"""
    name = settings.MARKET_DATA_PROVIDER
    if name == "iss":
        return IssProvider(
            settings.ISS_BASE_URL, settings.ISS_BOARD, settings.MARKET_DATA_TIMEOUT
        )
    if name == "tinvest":
        return TinvestProvider(
            settings.TINVEST_TOKEN,
            settings.TINVEST_TARGET,
            settings.TINVEST_ROOT_CA_PATH,
        )
    raise ImproperlyConfigured(f"Неизвестный MARKET_DATA_PROVIDER: {name}")
