from datetime import date, timedelta

import requests

from .base import Candle, InstrumentInfo, MarketDataError, MarketDataProvider

# Тип бумаги SECTYPE: 1 — обыкновенная акция, 2 — привилегированная,
# D — депозитарная расписка. Остальное в режиме TQBR — паи фондов.
SHARE_SECTYPES = frozenset({"1", "2", "D"})
ACTIVE_STATUS = "A"
TRADING_STATUS = "T"

SYNTHETIC_FIGI_PREFIX = "ISS-"

# ISS называет рубль устаревшим кодом SUR
CURRENCY_CODES = {"SUR": "rub", "RUR": "rub"}


def choose_price(security, marketdata):
    """Выбрать цену: на торгах последнюю сделку, вне торгов цену закрытия"""
    if marketdata.get("TRADINGSTATUS") == TRADING_STATUS:
        candidates = ("LAST", "LCURRENTPRICE", "LCLOSEPRICE")
    else:
        candidates = ("LCLOSEPRICE", "LAST", "LCURRENTPRICE")

    for column in candidates:
        if marketdata.get(column):
            return float(marketdata[column])
    for column in ("PREVLEGALCLOSEPRICE", "PREVPRICE"):
        if security.get(column):
            return float(security[column])
    return None


class IssProvider(MarketDataProvider):
    """Публичное API Мосбиржи ISS: без авторизации, данные с задержкой около 15 минут"""

    def __init__(self, base_url, board, timeout):
        self.base_url = base_url.rstrip("/")
        self.board = board
        self.timeout = timeout
        self.board_path = f"/engines/stock/markets/shares/boards/{board}/securities"

    def _get(self, path, **params):
        try:
            response = requests.get(
                f"{self.base_url}{path}.json",
                params={"iss.meta": "off", **params},
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as e:
            raise MarketDataError(f"Ошибка запроса к ISS: {e}") from e

    @staticmethod
    def _rows(payload, block):
        try:
            table = payload[block]
            return [dict(zip(table["columns"], row)) for row in table["data"]]
        except (KeyError, TypeError) as e:
            raise MarketDataError(f"Неожиданный формат ответа ISS: {block}") from e

    def list_shares(self):
        payload = self._get(
            self.board_path,
            **{
                "iss.only": "securities",
                "securities.columns": "SECID,SECNAME,ISIN,CURRENCYID,SECTYPE,STATUS",
            },
        )
        return [
            self._to_instrument(row)
            for row in self._rows(payload, "securities")
            if row["SECTYPE"] in SHARE_SECTYPES and row["STATUS"] == ACTIVE_STATUS
        ]

    def _to_instrument(self, row):
        ticker = row["SECID"]
        return InstrumentInfo(
            figi=f"{SYNTHETIC_FIGI_PREFIX}{ticker}",
            isin=row["ISIN"],
            name=row["SECNAME"],
            ticker=ticker,
            currency=CURRENCY_CODES.get(row["CURRENCYID"], row["CURRENCYID"].lower()),
            uid=f"iss:{self.board}:{ticker}",
        )

    def get_last_prices(self, shares):
        payload = self._get(
            self.board_path,
            **{
                "iss.only": "securities,marketdata",
                "securities.columns": "SECID,PREVLEGALCLOSEPRICE,PREVPRICE",
                "marketdata.columns": "SECID,TRADINGSTATUS,LAST,LCURRENTPRICE,LCLOSEPRICE",
            },
        )
        securities = {row["SECID"]: row for row in self._rows(payload, "securities")}
        marketdata = {row["SECID"]: row for row in self._rows(payload, "marketdata")}

        prices = {}
        for share in shares:
            if share.ticker not in securities:
                continue
            price = choose_price(
                securities[share.ticker], marketdata.get(share.ticker, {})
            )
            if price is not None:
                prices[share.ticker] = price
        return prices

    def get_daily_candles(self, share, days):
        date_from = (date.today() - timedelta(days=days)).isoformat()
        candles = []
        while True:
            payload = self._get(
                f"{self.board_path}/{share.ticker}/candles",
                interval=24,
                start=len(candles),
                **{"from": date_from},
            )
            rows = self._rows(payload, "candles")
            if not rows:
                return candles
            candles += [
                Candle(date=date.fromisoformat(row["begin"][:10]), close=row["close"])
                for row in rows
            ]
