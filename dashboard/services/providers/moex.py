from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Sequence
from zoneinfo import ZoneInfo

import requests
from django.utils import timezone

from dashboard.models import Share
from dashboard.services.market_data import HistoricalPrice, Instrument, Quote

ISS_BASE_URL = (
    "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR"
)
MOSCOW = ZoneInfo("Europe/Moscow")


class MoexProvider:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "InvestingDemo/1.0"})

    def _get_json(self, path: str, params: dict[str, str]) -> dict:
        response = self.session.get(
            f"{ISS_BASE_URL}/{path}.json", params=params, timeout=15
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Unexpected response from MOEX ISS.")
        return payload

    @staticmethod
    def _rows(payload: dict, section: str) -> list[dict]:
        block = payload.get(section)
        if not isinstance(block, dict):
            raise ValueError(f"MOEX ISS response does not contain {section!r}.")
        columns = block.get("columns")
        data = block.get("data")
        if not isinstance(columns, list) or not isinstance(data, list):
            raise ValueError(f"Invalid {section!r} block in MOEX ISS response.")
        return [dict(zip(columns, row, strict=True)) for row in data]

    def list_instruments(self) -> list[Instrument]:
        payload = self._get_json(
            "securities",
            {
                "iss.meta": "off",
                "iss.only": "securities",
                "securities.columns": (
                    "SECID,BOARDID,SHORTNAME,SECNAME,ISIN,CURRENCYID"
                ),
            },
        )
        instruments = []
        for row in self._rows(payload, "securities"):
            ticker = str(row.get("SECID") or "").strip()
            isin = str(row.get("ISIN") or "").strip()
            name = str(row.get("SHORTNAME") or row.get("SECNAME") or "").strip()
            if not ticker or len(ticker) > 10 or not isin or not name:
                continue

            board = str(row.get("BOARDID") or "TQBR").strip()
            identity = f"MOEX:{board}:{ticker}"
            currency = str(row.get("CURRENCYID") or "SUR").strip().upper()
            instruments.append(
                Instrument(
                    figi=identity,
                    isin=isin,
                    uid=identity,
                    ticker=ticker,
                    name=name,
                    currency={"SUR": "RUB"}.get(currency, currency).lower(),
                )
            )
        return instruments

    def get_quotes(self, shares: Sequence[Share]) -> dict[str, Quote]:
        if not shares:
            return {}

        payload = self._get_json(
            "securities",
            {
                "iss.meta": "off",
                "iss.only": "securities,marketdata",
                "securities.columns": "SECID,PREVPRICE",
                "marketdata.columns": (
                    "SECID,TRADINGSTATUS,LCURRENTPRICE,LCLOSEPRICE,"
                    "CLOSEPRICE,LAST,UPDATETIME,SYSTIME"
                ),
            },
        )
        previous_prices = {
            row["SECID"]: row.get("PREVPRICE")
            for row in self._rows(payload, "securities")
        }
        market_data = {
            row["SECID"]: row for row in self._rows(payload, "marketdata")
        }

        quotes = {}
        for share in shares:
            quote = market_data.get(share.ticker)
            if not quote:
                continue

            if quote.get("TRADINGSTATUS") == "T":
                candidates = (quote.get("LCURRENTPRICE"), quote.get("LAST"))
            else:
                candidates = (
                    quote.get("LAST"),
                    quote.get("LCLOSEPRICE"),
                    quote.get("CLOSEPRICE"),
                    previous_prices.get(share.ticker),
                )
            price = next(
                (
                    self._decimal(value)
                    for value in candidates
                    if value is not None
                ),
                None,
            )
            if price is not None:
                quotes[share.figi] = Quote(
                    price=price, observed_at=self._quote_time(quote)
                )
        return quotes

    def get_history(self, share: Share, days: int = 180) -> list[HistoricalPrice]:
        today = timezone.now().astimezone(MOSCOW).date()
        payload = self._get_json(
            f"securities/{share.ticker}/candles",
            {
                "iss.meta": "off",
                "from": (today - timedelta(days=days)).isoformat(),
                "till": today.isoformat(),
                "interval": "24",
            },
        )
        prices = []
        for row in self._rows(payload, "candles"):
            close = row.get("close")
            begin = row.get("begin")
            if close is not None and begin:
                prices.append(
                    HistoricalPrice(
                        time=datetime.fromisoformat(begin).date(),
                        close=self._decimal(close),
                    )
                )
        return prices

    @staticmethod
    def _decimal(value) -> Decimal:
        return Decimal(str(value))

    @staticmethod
    def _quote_time(row: dict) -> datetime:
        system_time = row.get("SYSTIME")
        if system_time:
            parsed = datetime.fromisoformat(system_time)
            return (
                timezone.make_aware(parsed, MOSCOW)
                if timezone.is_naive(parsed)
                else parsed
            )

        update_time = row.get("UPDATETIME")
        if update_time:
            return datetime.combine(
                timezone.now().astimezone(MOSCOW).date(),
                time.fromisoformat(update_time),
                tzinfo=MOSCOW,
            )
        return timezone.now()
