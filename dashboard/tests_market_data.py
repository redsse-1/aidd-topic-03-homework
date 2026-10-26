from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings

from dashboard.models import Share
from dashboard.services.graph import get_graph
from dashboard.services.market_data import (
    HistoricalPrice,
    Quote,
    get_market_data_provider,
)
from dashboard.services.providers.moex import MoexProvider
from dashboard.tasks import update_last_price


class MarketDataProviderTests(SimpleTestCase):
    def test_graph_renders_with_current_plotly_api(self):
        share = Share(ticker="SBER")
        history = [
            HistoricalPrice(date(2026, 10, 23), Decimal("292.32")),
            HistoricalPrice(date(2026, 10, 26), Decimal("296.1")),
        ]
        with patch("dashboard.services.graph.get_market_data_provider") as factory:
            factory.return_value.get_history.return_value = history
            graph = get_graph(share)

        self.assertIn("<div", graph)
        self.assertIn("plotly", graph.lower())

    def test_moex_maps_iss_instruments_to_share_fields(self):
        provider = MoexProvider()
        payload = {
            "securities": {
                "columns": [
                    "SECID",
                    "BOARDID",
                    "SHORTNAME",
                    "SECNAME",
                    "ISIN",
                    "CURRENCYID",
                ],
                "data": [
                    [
                        "SBER",
                        "TQBR",
                        "Сбербанк",
                        "Сбербанк России ПАО ао",
                        "RU0009029540",
                        "SUR",
                    ]
                ],
            }
        }
        with patch.object(provider, "_get_json", return_value=payload):
            instrument = provider.list_instruments()[0]

        self.assertEqual(instrument.figi, "MOEX:TQBR:SBER")
        self.assertEqual(instrument.uid, "MOEX:TQBR:SBER")
        self.assertEqual(instrument.isin, "RU0009029540")
        self.assertEqual(instrument.ticker, "SBER")
        self.assertEqual(instrument.name, "Сбербанк")
        self.assertEqual(instrument.currency, "rub")

    def test_moex_fetches_quotes_in_one_batch_and_uses_last_close_out_of_session(self):
        provider = MoexProvider()
        payload = {
            "securities": {
                "columns": ["SECID", "PREVPRICE"],
                "data": [["SBER", 292.32], ["GAZP", 112.57]],
            },
            "marketdata": {
                "columns": [
                    "SECID",
                    "TRADINGSTATUS",
                    "LCURRENTPRICE",
                    "LCLOSEPRICE",
                    "CLOSEPRICE",
                    "LAST",
                    "UPDATETIME",
                    "SYSTIME",
                ],
                "data": [
                    ["SBER", "T", 296.01, 295.75, 294.34, 296.05, None, None],
                    ["GAZP", "N", 114.59, None, None, 114.66, None, None],
                ],
            },
        }
        shares = [
            Share(figi="MOEX:TQBR:SBER", ticker="SBER"),
            Share(figi="MOEX:TQBR:GAZP", ticker="GAZP"),
        ]
        with patch.object(provider, "_get_json", return_value=payload) as get_json:
            quotes = provider.get_quotes(shares)

        self.assertEqual(quotes["MOEX:TQBR:SBER"].price, Decimal("296.01"))
        self.assertEqual(quotes["MOEX:TQBR:GAZP"].price, Decimal("114.66"))
        get_json.assert_called_once()

    @override_settings(MARKET_DATA_PROVIDER="t-invest", TINVEST_TOKEN="")
    def test_t_invest_sdk_is_not_imported_until_provider_is_used(self):
        provider = get_market_data_provider()
        with self.assertRaises(ImproperlyConfigured):
            provider.list_instruments()


class UpdatePriceTaskTests(TestCase):
    def test_task_fetches_batch_and_persists_decimal_price_and_trend(self):
        share = Share.objects.create(
            figi="MOEX:TQBR:SBER",
            isin="RU0009029540",
            name="Сбербанк",
            ticker="SBER",
            currency="rub",
            uid="MOEX:TQBR:SBER",
            last_price=Decimal("296.10"),
            is_trend_high=False,
        )
        quote_time = datetime(2026, 10, 26, 10, 0, tzinfo=timezone.utc)
        with patch("dashboard.tasks.get_market_data_provider") as provider_factory:
            provider_factory.return_value.get_quotes.return_value = {
                share.figi: Quote(Decimal("296.123456789"), quote_time)
            }
            updated_count = update_last_price()

        share.refresh_from_db()
        self.assertEqual(updated_count, 1)
        self.assertEqual(share.last_price, Decimal("296.123456789"))
        self.assertTrue(share.is_trend_high)
        self.assertEqual(share.updated_at, quote_time)
        provider_factory.return_value.get_quotes.assert_called_once()
