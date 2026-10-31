from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime


class MarketDataError(Exception):
    """Источник рыночных данных недоступен или вернул некорректный ответ"""


@dataclass(frozen=True)
class InstrumentInfo:
    """Акция в источнике данных"""

    figi: str
    isin: str
    name: str
    ticker: str
    currency: str
    uid: str


@dataclass(frozen=True)
class Quote:
    """Цена акции. time — время сделки или None, если это не цена сделки на торгах."""

    price: float
    time: datetime | None = None


@dataclass(frozen=True)
class Candle:
    """Дневная свеча"""

    date: date
    close: float


class MarketDataProvider(ABC):
    """Источник рыночных данных. Методы при сбое бросают MarketDataError."""

    @abstractmethod
    def list_shares(self):
        """Вернуть список InstrumentInfo по всем доступным акциям"""

    @abstractmethod
    def get_last_prices(self, shares):
        """Вернуть словарь {ticker: Quote} одним запросом. Акций без цены в нём нет."""

    @abstractmethod
    def get_daily_candles(self, share, days):
        """Вернуть дневные свечи Candle за последние days дней"""
