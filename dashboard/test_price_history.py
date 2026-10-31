from datetime import date, datetime, timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from dashboard.forms import PeriodForm
from dashboard.models import PriceRecord, Share
from dashboard.services.market_data import Candle, MarketDataError, Quote
from dashboard.services.market_data.iss import trade_time
from dashboard.services.price_history import (
    PricePoint,
    backfill_history,
    change_between,
    compute_stats,
    daily_changes,
    get_series,
    prune_quotes,
    record_quotes,
    refresh_daily_history,
    save_daily_candles,
)
from dashboard.services.shares import update_last_prices
from dashboard.tasks import update_price_history
from dashboard.test_market_data import FakeProvider, make_share


def moment(day, hour=0, minute=0):
    return timezone.make_aware(datetime.combine(day, datetime.min.time())) + timedelta(
        hours=hour, minutes=minute
    )


def add_daily(share, day, price):
    return PriceRecord.objects.create(
        share=share, kind=PriceRecord.Kind.DAILY, recorded_at=moment(day), price=price
    )


def add_quote(share, day, hour, price):
    return PriceRecord.objects.create(
        share=share,
        kind=PriceRecord.Kind.QUOTE,
        recorded_at=moment(day, hour),
        price=price,
    )


class TradeTimeTests(SimpleTestCase):
    def market(self, **kwargs):
        defaults = {
            "TRADINGSTATUS": "T",
            "LAST": 100.0,
            "TIME": "10:01:07",
            "SYSTIME": "2026-10-31 10:16:08",
        }
        return {**defaults, **kwargs}

    def test_trade_time_uses_moscow_time_of_the_deal(self):
        self.assertEqual(
            trade_time(self.market()),
            timezone.make_aware(datetime(2026, 10, 31, 10, 1, 7)),
        )

    def test_no_time_outside_trading(self):
        self.assertIsNone(trade_time(self.market(TRADINGSTATUS="N")))

    def test_no_time_without_deals(self):
        self.assertIsNone(trade_time(self.market(LAST=None)))

    def test_delayed_deal_before_midnight_keeps_its_date(self):
        result = trade_time(
            self.market(TIME="23:49:50", SYSTIME="2026-11-01 00:04:52")
        )
        self.assertEqual(result, timezone.make_aware(datetime(2026, 10, 31, 23, 49, 50)))


class RecordQuotesTests(TestCase):
    def setUp(self):
        self.share = make_share("SBER", last_price=100.0)
        self.deal = timezone.make_aware(datetime(2026, 10, 30, 12, 0))

    def provider(self, price, time):
        return FakeProvider(prices={"SBER": Quote(price, time)})

    def test_same_deal_is_saved_once(self):
        update_last_prices(self.provider(101.0, self.deal))
        update_last_prices(self.provider(101.0, self.deal))
        self.assertEqual(PriceRecord.objects.count(), 1)

    def test_new_deal_is_saved(self):
        update_last_prices(self.provider(101.0, self.deal))
        update_last_prices(self.provider(102.0, self.deal + timedelta(minutes=5)))
        self.assertEqual(PriceRecord.objects.count(), 2)

    def test_price_outside_trading_is_not_saved(self):
        update_last_prices(self.provider(100.0, None))
        self.share.refresh_from_db()
        self.assertEqual(self.share.last_price, 100.0)
        self.assertFalse(PriceRecord.objects.exists())

    def test_unknown_ticker_is_skipped(self):
        record_quotes([self.share], {"GAZP": Quote(1.0, self.deal)})
        self.assertFalse(PriceRecord.objects.exists())

    def test_database_rejects_duplicates(self):
        add_daily(self.share, date(2026, 10, 1), 1.0)
        with self.assertRaises(IntegrityError), transaction.atomic():
            add_daily(self.share, date(2026, 10, 1), 2.0)


class BackfillTests(TestCase):
    def setUp(self):
        self.share = make_share("SBER")
        self.today = timezone.localdate()
        self.yesterday = self.today - timedelta(days=1)

    def test_repeated_backfill_makes_no_duplicates_and_updates_price(self):
        save_daily_candles(self.share, [Candle(self.yesterday, 100.0)])
        save_daily_candles(self.share, [Candle(self.yesterday, 101.0)])
        self.assertEqual(PriceRecord.objects.get().price, 101.0)

    def test_unfinished_day_is_skipped(self):
        saved = save_daily_candles(self.share, [Candle(self.today, 100.0)])
        self.assertEqual(saved, 0)
        self.assertFalse(PriceRecord.objects.exists())

    def test_failure_of_one_share_does_not_stop_others(self):
        other = make_share("GAZP")

        class Provider(FakeProvider):
            def get_daily_candles(provider, share, days):
                if share.ticker == "SBER":
                    raise MarketDataError("down")
                return [Candle(self.yesterday, 5.0)]

        with self.assertLogs("dashboard.services.price_history", level="ERROR"):
            saved, failed = backfill_history(
                Provider(), [self.share, other], lambda share: 30
            )
        self.assertEqual((saved, failed), (1, 1))

    @override_settings(HISTORY_BACKFILL_DAYS=365, HISTORY_REQUEST_PAUSE=0)
    def test_refresh_loads_full_history_only_for_new_shares(self):
        new_share = make_share("NEW")
        add_daily(self.share, self.yesterday, 1.0)
        requested = {}

        class Provider(FakeProvider):
            def get_daily_candles(provider, share, days):
                requested[share.ticker] = days
                return []

        refresh_daily_history(Provider())

        self.assertEqual(requested[self.share.ticker], 7)
        self.assertEqual(requested[new_share.ticker], 365)

    @override_settings(HISTORY_REQUEST_PAUSE=0)
    def test_command(self):
        provider = FakeProvider(candles=[Candle(self.yesterday, 100.0)])
        out = StringIO()
        target = "dashboard.management.commands.backfill_prices.get_provider"
        with mock.patch(target, return_value=provider):
            call_command("backfill_prices", "--ticker", "SBER", stdout=out)
            call_command("backfill_prices", "--ticker", "SBER", stdout=out)
        self.assertEqual(PriceRecord.objects.count(), 1)

    @override_settings(HISTORY_REQUEST_PAUSE=0)
    def test_command_fails_when_nothing_is_loaded(self):
        provider = FakeProvider(error=MarketDataError("down"))
        target = "dashboard.management.commands.backfill_prices.get_provider"
        with mock.patch(target, return_value=provider):
            with self.assertLogs("dashboard.services.price_history", level="ERROR"):
                with self.assertRaises(CommandError):
                    call_command("backfill_prices", stdout=StringIO())

    def test_command_without_shares(self):
        Share.objects.all().delete()
        with self.assertRaises(CommandError):
            call_command("backfill_prices", stdout=StringIO())

    @override_settings(HISTORY_QUOTE_RETENTION_DAYS=30)
    def test_old_quotes_are_pruned_but_closes_stay(self):
        old_day = self.today - timedelta(days=40)
        add_quote(self.share, old_day, 12, 1.0)
        add_quote(self.share, self.yesterday, 12, 2.0)
        add_daily(self.share, old_day, 3.0)

        self.assertEqual(prune_quotes(), 1)

        self.assertEqual(PriceRecord.objects.count(), 2)

    @override_settings(HISTORY_REQUEST_PAUSE=0, HISTORY_QUOTE_RETENTION_DAYS=30)
    def test_nightly_task(self):
        add_quote(self.share, self.today - timedelta(days=40), 12, 1.0)
        provider = FakeProvider(candles=[Candle(self.yesterday, 100.0)])
        with mock.patch("dashboard.tasks.get_provider", return_value=provider):
            update_price_history()
        record = PriceRecord.objects.get()
        self.assertEqual(record.kind, PriceRecord.Kind.DAILY)


class SeriesTests(TestCase):
    def setUp(self):
        self.share = make_share("SBER")
        self.today = timezone.localdate()
        self.day = self.today - timedelta(days=2)
        add_daily(self.share, self.day, 100.0)
        add_quote(self.share, self.day, 12, 99.0)
        add_quote(self.share, self.today, 12, 101.0)

    def prices(self, start, end):
        return [point.price for point in get_series(self.share, start, end)]

    def test_closed_day_uses_close_and_current_day_uses_quotes(self):
        start = self.today - timedelta(days=30)
        self.assertEqual(self.prices(start, self.today), [100.0, 101.0])

    def test_short_period_shows_quotes(self):
        start = self.today - timedelta(days=7)
        self.assertEqual(self.prices(start, self.today), [99.0, 101.0])

    def test_whole_history(self):
        self.assertEqual(self.prices(None, self.today), [100.0, 101.0])

    def test_range_borders_are_included(self):
        self.assertEqual(len(self.prices(self.day, self.day)), 1)

    def test_other_share_is_not_mixed_in(self):
        add_daily(make_share("GAZP"), self.day, 5.0)
        self.assertEqual(self.prices(None, self.today), [100.0, 101.0])


class StatsTests(SimpleTestCase):
    def points(self, *prices):
        return [
            PricePoint(moment(date(2026, 10, 1) + timedelta(days=i)), price)
            for i, price in enumerate(prices)
        ]

    def test_change(self):
        self.assertEqual(change_between(200.0, 250.0), (50.0, 25.0))
        self.assertEqual(change_between(200.0, 150.0), (-50.0, -25.0))

    def test_change_from_zero_has_no_percent(self):
        self.assertEqual(change_between(0.0, 5.0), (5.0, None))

    def test_stats(self):
        stats = compute_stats(self.points(100.0, 120.0, 90.0, 110.0))
        self.assertEqual(stats["change"], 10.0)
        self.assertEqual(stats["percent"], 10.0)
        self.assertEqual(stats["min_price"], 90.0)
        self.assertEqual(stats["min_date"], date(2026, 10, 3))
        self.assertEqual(stats["max_price"], 120.0)
        self.assertEqual(stats["average"], 105.0)
        self.assertEqual((stats["up_days"], stats["down_days"]), (2, 1))
        self.assertEqual(stats["points"], 4)

    def test_float_noise_is_rounded(self):
        self.assertEqual(change_between(0.1, 0.3)[0], 0.2)

    def test_no_points(self):
        self.assertIsNone(compute_stats([]))
        self.assertEqual(daily_changes([]), [])

    def test_single_point(self):
        stats = compute_stats(self.points(100.0))
        self.assertEqual((stats["change"], stats["percent"]), (0.0, 0.0))

    def test_daily_changes_are_newest_first(self):
        rows = daily_changes(self.points(100.0, 110.0))
        self.assertEqual(rows[0]["change"], 10.0)
        self.assertEqual(rows[0]["percent"], 10.0)
        self.assertIsNone(rows[1]["change"])


class PeriodFormTests(SimpleTestCase):
    def range_of(self, **data):
        form = PeriodForm(data)
        self.assertTrue(form.is_valid())
        return form.get_range()

    def test_default_is_six_months(self):
        start, end = self.range_of()
        self.assertEqual(end - start, timedelta(days=180))

    def test_all_has_no_start(self):
        self.assertIsNone(self.range_of(period="all")[0])

    def test_custom_range(self):
        self.assertEqual(
            self.range_of(date_from="2026-10-01", date_to="2026-10-10"),
            (date(2026, 10, 1), date(2026, 10, 10)),
        )

    def test_custom_end_defaults_to_today(self):
        start, end = self.range_of(date_from="2026-10-01")
        self.assertEqual(end, timezone.localdate())

    def test_invalid_values(self):
        for data in (
            {"period": "nope"},
            {"date_from": "garbage"},
            {"date_from": "2026-10-10", "date_to": "2026-10-01"},
        ):
            self.assertFalse(PeriodForm(data).is_valid(), data)


class DetailPageTests(TestCase):
    def setUp(self):
        self.share = make_share("SBER", last_price=296.4)
        self.url = reverse("dashboard:detail", args=[self.share.id])
        self.yesterday = timezone.localdate() - timedelta(days=1)

    def test_page_does_not_call_the_provider(self):
        add_daily(self.share, self.yesterday, 100.0)
        with mock.patch("dashboard.services.market_data.get_provider") as provider:
            response = self.client.get(self.url)
        provider.assert_not_called()
        self.assertContains(response, "plotly-graph-div")
        self.assertContains(response, "height:450px")
        self.assertContains(response, "296,4")

    def test_stats_and_changes_are_shown(self):
        add_daily(self.share, self.yesterday - timedelta(days=1), 100.0)
        add_daily(self.share, self.yesterday, 125.0)
        response = self.client.get(self.url, {"period": "1m"})
        self.assertContains(response, "25,00 rub")
        self.assertContains(response, "(25,00%)")
        self.assertContains(response, "Изменения по дням")
        self.assertEqual(response.context["selected_period"], "1m")

    def test_empty_history(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "истории цен нет")
        self.assertNotContains(response, "plotly-graph-div")

    def test_invalid_period_shows_error(self):
        response = self.client.get(
            self.url, {"date_from": "2026-10-10", "date_to": "2026-10-01"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Начальная дата позже конечной")

    def test_custom_range_filters_points(self):
        add_daily(self.share, date(2026, 1, 15), 10.0)
        add_daily(self.share, date(2026, 3, 15), 20.0)
        response = self.client.get(
            self.url, {"date_from": "2026-01-01", "date_to": "2026-01-31"}
        )
        self.assertEqual(response.context["stats"]["points"], 1)


class HistoryApiTests(APITestCase):
    def setUp(self):
        self.share = make_share("SBER")
        self.yesterday = timezone.localdate() - timedelta(days=1)
        add_daily(self.share, self.yesterday - timedelta(days=1), 100.0)
        add_daily(self.share, self.yesterday, 110.0)
        self.url = f"/api/v1/shares/{self.share.id}/history/"

    def test_anonymous_client_can_read(self):
        response = self.client.get(self.url, {"period": "1m"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(body["stats"]["percent"], 10.0)
        self.assertEqual([point["price"] for point in body["points"]], [100.0, 110.0])
        self.assertTrue(
            body["points"][-1]["time"].startswith(f"{self.yesterday}T00:00:00+03:00")
        )

    def test_invalid_period(self):
        response = self.client.get(self.url, {"period": "nope"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_share(self):
        response = self.client.get(f"/api/v1/shares/{self.share.id + 1}/history/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_history_is_deleted_with_share(self):
        user = get_user_model().objects.create_user("api@test.local")
        self.client.force_authenticate(user)
        self.client.delete(f"/api/v1/shares/{self.share.id}/")
        self.assertFalse(PriceRecord.objects.exists())
