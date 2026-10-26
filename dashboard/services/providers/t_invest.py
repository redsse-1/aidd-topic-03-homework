from contextlib import contextmanager
from datetime import datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterator, Sequence

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from dashboard.models import Share
from dashboard.services.market_data import HistoricalPrice, Instrument, Quote


class TInvestProvider:
    @staticmethod
    @contextmanager
    def _client() -> Iterator:
        if not settings.TINVEST_TOKEN:
            raise ImproperlyConfigured(
                "Set TINVEST_TOKEN to use MARKET_DATA_PROVIDER=t-invest."
            )

        if settings.TINVEST_ROOT_CERT_PATH:
            import grpc
            from tinkoff.invest.services import Services

            certificate_path = Path(settings.TINVEST_ROOT_CERT_PATH)
            try:
                certificate = certificate_path.read_bytes()
            except OSError as error:
                raise ImproperlyConfigured(
                    f"Cannot read TINVEST_ROOT_CERT_PATH: {certificate_path}"
                ) from error
            channel = grpc.secure_channel(
                settings.TINVEST_API_TARGET,
                grpc.ssl_channel_credentials(root_certificates=certificate),
            )
            try:
                yield Services(channel, token=settings.TINVEST_TOKEN)
            finally:
                channel.close()
            return

        from tinkoff.invest import Client

        with Client(
            settings.TINVEST_TOKEN, target=settings.TINVEST_API_TARGET
        ) as client:
            yield client

    def list_instruments(self) -> list[Instrument]:
        with self._client() as client:
            response = client.instruments.shares()
        return [
            Instrument(
                figi=share.figi,
                isin=share.isin or "",
                uid=share.uid,
                ticker=share.ticker,
                name=share.name,
                currency=share.currency,
            )
            for share in response.instruments
            if share.figi and share.uid and share.ticker
        ]

    def get_quotes(self, shares: Sequence[Share]) -> dict[str, Quote]:
        shares = [share for share in shares if not share.figi.startswith("MOEX:")]
        if not shares:
            return {}

        with self._client() as client:
            response = client.market_data.get_last_prices(
                figi=[share.figi for share in shares]
            )
        return {
            quote.figi: Quote(
                price=self._money(quote.price),
                observed_at=quote.time,
            )
            for quote in response.last_prices
        }

    def get_history(self, share: Share, days: int = 180) -> list[HistoricalPrice]:
        if share.figi.startswith("MOEX:"):
            return []

        from tinkoff.invest import CandleInterval

        start = datetime.now(datetime_timezone.utc) - timedelta(days=days)
        with self._client() as client:
            candles = client.get_all_candles(
                figi=share.figi,
                from_=start,
                interval=CandleInterval.CANDLE_INTERVAL_DAY,
            )
            return [
                HistoricalPrice(
                    time=candle.time.date(),
                    close=self._money(candle.close),
                )
                for candle in candles
            ]

    @staticmethod
    def _money(value) -> Decimal:
        return Decimal(value.units) + Decimal(value.nano) / Decimal(1_000_000_000)
