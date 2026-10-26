from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from importlib import import_module
from typing import Protocol, Sequence

from dashboard.models import Share


@dataclass(frozen=True)
class Instrument:
    figi: str
    isin: str
    uid: str
    ticker: str
    name: str
    currency: str


@dataclass(frozen=True)
class Quote:
    price: Decimal
    observed_at: datetime


@dataclass(frozen=True)
class HistoricalPrice:
    time: date
    close: Decimal


class MarketDataProvider(Protocol):
    def list_instruments(self) -> list[Instrument]: ...

    def get_quotes(self, shares: Sequence[Share]) -> dict[str, Quote]: ...

    def get_history(
        self, share: Share, days: int = 180
    ) -> list[HistoricalPrice]: ...


def get_market_data_provider() -> MarketDataProvider:
    from django.conf import settings

    providers = {
        "moex": "dashboard.services.providers.moex.MoexProvider",
        "t-invest": "dashboard.services.providers.t_invest.TInvestProvider",
    }
    try:
        module_path, class_name = providers[settings.MARKET_DATA_PROVIDER].rsplit(
            ".", 1
        )
    except KeyError as error:
        choices = ", ".join(sorted(providers))
        raise ValueError(
            f"Unknown MARKET_DATA_PROVIDER {settings.MARKET_DATA_PROVIDER!r}; "
            f"choose one of: {choices}."
        ) from error

    provider_class = getattr(import_module(module_path), class_name)
    return provider_class()
