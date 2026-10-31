import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest import mock

import requests
from django.core.exceptions import ImproperlyConfigured
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone as django_timezone

from dashboard.models import Share
from dashboard.services.market_data import (
    Candle,
    InstrumentInfo,
    MarketDataError,
    MarketDataProvider,
    Quote,
    get_provider,
)
from dashboard.services.market_data.iss import IssProvider, choose_price
from dashboard.services.market_data.tinvest import TinvestProvider
from dashboard.services.shares import (
    compute_trend,
    sync_shares,
    update_last_prices,
)
from dashboard.tasks import update_last_price


class FakeProvider(MarketDataProvider):
    def __init__(self, instruments=(), prices=None, candles=(), error=None):
        self.instruments = instruments
        self.prices = prices or {}
        self.candles = candles
        self.error = error
        self.price_calls = 0

    def _fail_if_needed(self):
        if self.error:
            raise self.error

    def list_shares(self):
        self._fail_if_needed()
        return list(self.instruments)

    def get_last_prices(self, shares):
        self._fail_if_needed()
        self.price_calls += 1
        return self.prices

    def get_daily_candles(self, share, days):
        self._fail_if_needed()
        return list(self.candles)


def make_share(ticker="SBER", **kwargs):
    defaults = {
        "figi": f"figi-{ticker}",
        "isin": f"isin-{ticker}",
        "name": f"Company {ticker}",
        "currency": "rub",
    }
    return Share.objects.create(ticker=ticker, **{**defaults, **kwargs})


def iss_response(payload):
    response = mock.Mock()
    response.json.return_value = payload
    return response


def table(columns, *rows):
    return {"columns": columns, "data": list(rows)}


class ProviderSelectionTests(SimpleTestCase):
    def test_iss_is_used_by_setting(self):
        with override_settings(MARKET_DATA_PROVIDER="iss"):
            self.assertIsInstance(get_provider(), IssProvider)

    def test_tinvest_is_used_by_setting(self):
        with override_settings(MARKET_DATA_PROVIDER="tinvest"):
            self.assertIsInstance(get_provider(), TinvestProvider)

    def test_unknown_provider_is_rejected(self):
        with override_settings(MARKET_DATA_PROVIDER="unknown"):
            with self.assertRaises(ImproperlyConfigured):
                get_provider()


class ChoosePriceTests(SimpleTestCase):
    security = {"PREVLEGALCLOSEPRICE": 296.4, "PREVPRICE": 296.25}

    def test_last_trade_during_session(self):
        marketdata = {"TRADINGSTATUS": "T", "LAST": 300.5, "LCLOSEPRICE": 299.0}
        self.assertEqual(choose_price(self.security, marketdata), 300.5)

    def test_close_price_after_session(self):
        marketdata = {"TRADINGSTATUS": "N", "LAST": 300.5, "LCLOSEPRICE": 299.0}
        self.assertEqual(choose_price(self.security, marketdata), 299.0)

    def test_previous_close_before_session(self):
        marketdata = {"TRADINGSTATUS": "N", "LAST": None, "LCLOSEPRICE": None}
        self.assertEqual(choose_price(self.security, marketdata), 296.4)

    def test_no_price_at_all(self):
        self.assertIsNone(choose_price({}, {}))


class IssProviderTests(SimpleTestCase):
    def setUp(self):
        self.provider = IssProvider("https://iss.test/iss/", "TQBR", 5)

    @mock.patch("dashboard.services.market_data.iss.requests.get")
    def test_list_shares_maps_fields_and_skips_funds(self, get):
        columns = ["SECID", "SECNAME", "ISIN", "CURRENCYID", "SECTYPE", "STATUS"]
        get.return_value = iss_response(
            {
                "securities": table(
                    columns,
                    ["SBER", "Сбербанк ао", "RU0009029540", "SUR", "1", "A"],
                    ["SBERP", "Сбербанк ап", "RU0009029557", "SUR", "2", "A"],
                    ["AKBC", "БПИФ", "RU000A10B6F8", "SUR", "9", "A"],
                    ["OLD", "Неактивная", "RU0000000001", "SUR", "1", "N"],
                )
            }
        )

        shares = self.provider.list_shares()

        self.assertEqual([share.ticker for share in shares], ["SBER", "SBERP"])
        self.assertEqual(
            shares[0],
            InstrumentInfo(
                figi="ISS-SBER",
                isin="RU0009029540",
                name="Сбербанк ао",
                ticker="SBER",
                currency="rub",
                uid="iss:TQBR:SBER",
            ),
        )

    @mock.patch("dashboard.services.market_data.iss.requests.get")
    def test_last_prices_use_single_request(self, get):
        get.return_value = iss_response(
            {
                "securities": table(
                    ["SECID", "PREVLEGALCLOSEPRICE", "PREVPRICE"],
                    ["SBER", 296.4, 296.25],
                    ["GAZP", 120.5, 120.1],
                ),
                "marketdata": table(
                    [
                        "SECID",
                        "TRADINGSTATUS",
                        "LAST",
                        "LCURRENTPRICE",
                        "LCLOSEPRICE",
                        "TIME",
                        "SYSTIME",
                    ],
                    ["SBER", "T", 300.12, None, None, "10:01:07", "2026-10-31 10:16:08"],
                    ["GAZP", "N", None, None, None, "07:00:10", "2026-10-31 07:15:11"],
                ),
            }
        )
        shares = [SimpleNamespace(ticker=t) for t in ("SBER", "GAZP", "AAPL")]

        prices = self.provider.get_last_prices(shares)

        self.assertEqual(prices["SBER"].price, 300.12)
        self.assertEqual(
            prices["SBER"].time,
            django_timezone.make_aware(datetime(2026, 10, 31, 10, 1, 7)),
        )
        self.assertEqual(prices["GAZP"], Quote(120.5))
        self.assertNotIn("AAPL", prices)
        self.assertEqual(get.call_count, 1)

    @mock.patch("dashboard.services.market_data.iss.requests.get")
    def test_candles_are_read_page_by_page(self, get):
        columns = ["open", "close", "begin"]
        get.side_effect = [
            iss_response(
                {
                    "candles": table(
                        columns,
                        [1, 276.18, "2026-10-01 00:00:00"],
                        [2, 275.45, "2026-10-02 00:00:00"],
                    )
                }
            ),
            iss_response({"candles": table(columns, [3, 280.5, "2026-10-03 00:00:00"])}),
            iss_response({"candles": table(columns)}),
        ]

        candles = self.provider.get_daily_candles(SimpleNamespace(ticker="SBER"), 180)

        self.assertEqual(len(candles), 3)
        self.assertEqual(candles[0], Candle(date(2026, 10, 1), 276.18))
        self.assertEqual(get.call_args_list[1].kwargs["params"]["start"], 2)
        self.assertEqual(get.call_args_list[2].kwargs["params"]["start"], 3)

    @mock.patch(
        "dashboard.services.market_data.iss.requests.get",
        side_effect=requests.ConnectionError("no network"),
    )
    def test_network_error_becomes_market_data_error(self, get):
        with self.assertRaises(MarketDataError):
            self.provider.list_shares()

    @mock.patch("dashboard.services.market_data.iss.requests.get")
    def test_unexpected_format_becomes_market_data_error(self, get):
        get.return_value = iss_response({"unexpected": {}})
        with self.assertRaises(MarketDataError):
            self.provider.get_last_prices([])


class FakeTinvestClient:
    instances = []
    TRADE_TIME = datetime(2026, 10, 31, 7, 1, tzinfo=timezone.utc)

    def __init__(self, token, target=None):
        self.token = token
        self.target = target
        FakeTinvestClient.instances.append(self)
        quotation = SimpleNamespace(units=245, nano=900000000)
        self.market_data = SimpleNamespace(
            get_last_prices=lambda figi: SimpleNamespace(
                last_prices=[
                    SimpleNamespace(
                        figi=figi[0], price=quotation, time=self.TRADE_TIME
                    )
                ]
            )
        )
        self.instruments = SimpleNamespace(
            shares=lambda: SimpleNamespace(
                instruments=[
                    SimpleNamespace(
                        figi="BBG004730N88",
                        isin="RU0009029540",
                        name="Сбер",
                        ticker="SBER",
                        currency="rub",
                        uid="uid-1",
                    )
                ]
            )
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get_all_candles(self, figi, from_, interval):
        yield SimpleNamespace(
            time=datetime(2026, 10, 1, tzinfo=timezone.utc),
            close=SimpleNamespace(units=276, nano=180000000),
        )


def fake_sdk_modules():
    utils = SimpleNamespace(
        quotation_to_decimal=lambda q: Decimal(q.units) + Decimal(q.nano) / 10**9,
        now=lambda: datetime(2026, 10, 31, tzinfo=timezone.utc),
    )
    sdk = SimpleNamespace(
        Client=FakeTinvestClient,
        CandleInterval=SimpleNamespace(CANDLE_INTERVAL_DAY="day"),
    )
    return {
        "t_tech": SimpleNamespace(),
        "t_tech.invest": sdk,
        "t_tech.invest.utils": utils,
    }


class TinvestProviderTests(SimpleTestCase):
    share = SimpleNamespace(ticker="SBER", figi="BBG004730N88")

    def setUp(self):
        FakeTinvestClient.instances = []
        self.provider = TinvestProvider("token", "invest.test:443", "")

    def test_sdk_is_not_imported_with_the_application(self):
        self.assertNotIn("t_tech.invest", sys.modules)
        self.assertNotIn("tinkoff.invest", sys.modules)

    def test_missing_library_gives_clear_error(self):
        with mock.patch.dict(
            sys.modules, {"t_tech.invest": None, "tinkoff.invest": None}
        ):
            with self.assertRaisesRegex(MarketDataError, "не установлена"):
                self.provider.list_shares()

    def test_token_is_required(self):
        with self.assertRaisesRegex(MarketDataError, "TINVEST_TOKEN"):
            TinvestProvider("", "invest.test:443", "").list_shares()

    def test_list_shares(self):
        with mock.patch.dict(sys.modules, fake_sdk_modules()):
            shares = self.provider.list_shares()
        self.assertEqual(shares[0].figi, "BBG004730N88")
        self.assertEqual(FakeTinvestClient.instances[0].target, "invest.test:443")

    def test_last_price_keeps_fraction(self):
        with mock.patch.dict(sys.modules, fake_sdk_modules()):
            prices = self.provider.get_last_prices([self.share])
        self.assertEqual(prices["SBER"].price, 245.9)
        self.assertEqual(prices["SBER"].time, FakeTinvestClient.TRADE_TIME)

    def test_synthetic_figi_is_not_requested(self):
        share = SimpleNamespace(ticker="SBER", figi="ISS-SBER")
        with mock.patch.dict(sys.modules, fake_sdk_modules()):
            self.assertEqual(self.provider.get_last_prices([share]), {})
            self.assertEqual(self.provider.get_daily_candles(share, 180), [])
        self.assertEqual(FakeTinvestClient.instances, [])

    def test_candles(self):
        with mock.patch.dict(sys.modules, fake_sdk_modules()):
            candles = self.provider.get_daily_candles(self.share, 180)
        self.assertEqual(candles, [Candle(date(2026, 10, 1), 276.18)])

    def test_root_certificate_path_is_passed_to_grpc(self):
        provider = TinvestProvider("token", "invest.test:443", "C:/certs/root.pem")
        with mock.patch.dict(sys.modules, fake_sdk_modules()):
            with mock.patch.dict("os.environ"):
                provider.list_shares()
                self.assertEqual(
                    os.environ["GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"],
                    "C:/certs/root.pem",
                )


class ComputeTrendTests(SimpleTestCase):
    def test_rise_and_fall(self):
        self.assertIs(compute_trend(100.0, 101.0, None), True)
        self.assertIs(compute_trend(100.0, 99.0, True), False)

    def test_equal_price_keeps_trend(self):
        self.assertIs(compute_trend(100.0, 100.0, False), False)

    def test_first_price_has_no_trend(self):
        self.assertIsNone(compute_trend(None, 100.0, None))


class UpdateLastPricesTests(TestCase):
    def test_updates_price_trend_and_time_with_one_request(self):
        first = make_share("SBER", last_price=100.0, is_trend_high=True)
        second = make_share("GAZP", last_price=100.0, is_trend_high=True)
        untouched = make_share("AAPL", last_price=5.0)
        Share.objects.filter(id=first.id).update(updated_at=None)
        provider = FakeProvider(prices={"SBER": Quote(101.25), "GAZP": Quote(99.5)})

        self.assertEqual(update_last_prices(provider), 2)

        first.refresh_from_db()
        second.refresh_from_db()
        untouched.refresh_from_db()
        self.assertEqual(provider.price_calls, 1)
        self.assertEqual(first.last_price, 101.25)
        self.assertIs(first.is_trend_high, True)
        self.assertIsNotNone(first.updated_at)
        self.assertIs(second.is_trend_high, False)
        self.assertEqual(untouched.last_price, 5.0)

    def test_task_survives_provider_failure(self):
        share = make_share(last_price=100.0)
        provider = FakeProvider(error=MarketDataError("down"))
        with mock.patch("dashboard.tasks.get_provider", return_value=provider):
            with self.assertLogs("dashboard.tasks", level="ERROR"):
                update_last_price()
        share.refresh_from_db()
        self.assertEqual(share.last_price, 100.0)


class SyncSharesTests(TestCase):
    instrument = InstrumentInfo(
        figi="ISS-SBER",
        isin="RU0009029540",
        name="Сбербанк",
        ticker="SBER",
        currency="rub",
        uid="iss:TQBR:SBER",
    )

    def test_creates_and_updates_by_ticker(self):
        self.assertEqual(sync_shares(FakeProvider([self.instrument])), 1)

        renamed = InstrumentInfo(
            "BBG004730N88", "RU0009029540", "Сбер Банк", "SBER", "rub", "real-uid"
        )
        self.assertEqual(sync_shares(FakeProvider([renamed])), 1)

        share = Share.objects.get()
        self.assertEqual(share.name, "Сбер Банк")
        self.assertEqual(share.figi, "BBG004730N88")

    def test_conflict_does_not_stop_the_import(self):
        make_share("OTHER", figi="ISS-SBER")
        good = InstrumentInfo("ISS-GAZP", "RU1", "Газпром", "GAZP", "rub", "gazp")
        with self.assertLogs("dashboard.services.shares", level="ERROR"):
            saved = sync_shares(FakeProvider([self.instrument, good]))
        self.assertEqual(saved, 1)
        self.assertTrue(Share.objects.filter(ticker="GAZP").exists())

    def test_command_loads_shares(self):
        provider = FakeProvider([self.instrument])
        target = "dashboard.management.commands.add_shares.get_provider"
        with mock.patch(target, return_value=provider):
            call_command("add_shares", stdout=StringIO())
        self.assertEqual(Share.objects.count(), 1)

    def test_command_reports_provider_failure(self):
        provider = FakeProvider(error=MarketDataError("down"))
        target = "dashboard.management.commands.add_shares.get_provider"
        with mock.patch(target, return_value=provider):
            with self.assertRaises(CommandError):
                call_command("add_shares", stdout=StringIO())


class ShareDetailPageTests(TestCase):
    def setUp(self):
        self.share = make_share(last_price=296.4)
        self.url = reverse("dashboard:detail", args=[self.share.id])

    def test_missing_share_gives_404(self):
        response = self.client.get(reverse("dashboard:detail", args=[self.share.id + 1]))
        self.assertEqual(response.status_code, 404)


class ShareListPageTests(TestCase):
    def test_trend_colours(self):
        make_share("UP", last_price=1.0, is_trend_high=True)
        make_share("DOWN", last_price=1.0, is_trend_high=False)
        response = self.client.get(reverse("dashboard:index"))
        self.assertContains(response, "mediumseagreen", count=1)
        self.assertContains(response, "palevioletred", count=1)

    def test_unknown_trend_has_no_colour(self):
        make_share("NEW", last_price=1.0, is_trend_high=None)
        response = self.client.get(reverse("dashboard:index"))
        self.assertNotContains(response, "mediumseagreen")
        self.assertNotContains(response, "palevioletred")
