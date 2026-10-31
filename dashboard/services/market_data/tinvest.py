import importlib
import logging
import os
from datetime import timedelta

from .base import Candle, InstrumentInfo, MarketDataError, MarketDataProvider
from .iss import SYNTHETIC_FIGI_PREFIX

logger = logging.getLogger(__name__)

# Новое имя пакета SDK и прежнее
SDK_MODULES = ("t_tech.invest", "tinkoff.invest")


def load_sdk():
    """Импортировать SDK только при обращении к провайдеру: он необязателен"""
    for module in SDK_MODULES:
        try:
            return (
                importlib.import_module(module),
                importlib.import_module(f"{module}.utils"),
            )
        except ImportError:
            continue
    raise MarketDataError(
        "Библиотека T-Invest не установлена: см. requirements-tinvest.txt"
    )


class TinvestProvider(MarketDataProvider):
    """T-Invest API. Используются только методы чтения."""

    def __init__(self, token, target, root_ca_path):
        self.token = token
        self.target = target
        self.root_ca_path = root_ca_path

    def _client(self, sdk):
        if self.root_ca_path:
            os.environ["GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"] = self.root_ca_path
        return sdk.Client(self.token, target=self.target)

    def _call(self, request):
        """Выполнить запрос к API и привести любой сбой к MarketDataError"""
        if not self.token:
            raise MarketDataError("Не задана переменная окружения TINVEST_TOKEN")
        sdk, utils = load_sdk()
        try:
            with self._client(sdk) as client:
                return request(client, sdk, utils)
        except Exception as e:
            raise MarketDataError(f"Ошибка запроса к T-Invest: {e}") from e

    def list_shares(self):
        def request(client, sdk, utils):
            return [
                InstrumentInfo(
                    figi=item.figi,
                    isin=item.isin,
                    name=item.name,
                    ticker=item.ticker,
                    currency=item.currency,
                    uid=item.uid,
                )
                for item in client.instruments.shares().instruments
            ]

        return self._call(request)

    def get_last_prices(self, shares):
        # FIGI из ISS условный: такие акции T-Invest не знает
        tickers = {
            share.figi: share.ticker
            for share in shares
            if not share.figi.startswith(SYNTHETIC_FIGI_PREFIX)
        }
        if not tickers:
            logger.warning("Нет акций с настоящим FIGI: выполните add_shares")
            return {}

        def request(client, sdk, utils):
            response = client.market_data.get_last_prices(figi=list(tickers))
            return {
                tickers[item.figi]: float(utils.quotation_to_decimal(item.price))
                for item in response.last_prices
                if item.figi in tickers
            }

        return self._call(request)

    def get_daily_candles(self, share, days):
        if share.figi.startswith(SYNTHETIC_FIGI_PREFIX):
            return []

        def request(client, sdk, utils):
            return [
                Candle(
                    date=candle.time.date(),
                    close=float(utils.quotation_to_decimal(candle.close)),
                )
                for candle in client.get_all_candles(
                    figi=share.figi,
                    from_=utils.now() - timedelta(days=days),
                    interval=sdk.CandleInterval.CANDLE_INTERVAL_DAY,
                )
            ]

        return self._call(request)
