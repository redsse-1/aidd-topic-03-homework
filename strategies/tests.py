from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from dashboard.models import PriceRecord, Share
from dashboard.test_market_data import make_share
from dashboard.test_price_history import add_daily
from strategies.conditions import BuyCondition, SellCondition
from strategies.engine import SimulationError, max_drawdown, simulate, sma
from strategies.forms import StrategyForm
from strategies.models import SimulationResult, Strategy, VirtualTrade
from strategies.services import load_closes, run_simulation, update_auto_strategies
from strategies.tasks import update_strategies

User = get_user_model()
START = date(2026, 1, 1)


def rules(**kwargs):
    defaults = {
        "initial_capital": Decimal("1000"),
        "commission_percent": Decimal("0"),
        "buy_condition": BuyCondition.PRICE_BELOW,
        "buy_value": Decimal("100"),
        "sell_condition": SellCondition.PRICE_ABOVE,
        "sell_value": Decimal("120"),
        "stop_loss_percent": None,
        "lookback_days": 3,
        "sma_short": 2,
        "sma_long": 3,
    }
    return SimpleNamespace(**{**defaults, **kwargs})


def closes(*prices):
    return [
        (START + timedelta(days=index), Decimal(str(price)))
        for index, price in enumerate(prices)
    ]


class EngineTests(SimpleTestCase):
    def test_trade_is_filled_at_next_close(self):
        outcome = simulate(rules(), closes(100, 90, 95))
        buy = outcome.trades[0]
        self.assertEqual(buy.signal_date, START)
        self.assertEqual(buy.date, START + timedelta(days=1))
        self.assertEqual(buy.price, Decimal("90"))
        self.assertEqual(buy.quantity, 11)

    def test_signal_on_last_day_is_not_executed(self):
        outcome = simulate(rules(), closes(150, 90))
        self.assertEqual(outcome.trades, [])
        self.assertEqual(outcome.final_value, Decimal("1000.00"))

    def test_future_prices_do_not_change_past_decisions(self):
        short = simulate(rules(), closes(100, 90, 95))
        long = simulate(rules(), closes(100, 90, 95, 200, 50))
        self.assertEqual(long.trades[0], short.trades[0])

    def test_full_cycle_with_profit(self):
        outcome = simulate(rules(), closes(100, 100, 130, 140))
        self.assertEqual([t.side for t in outcome.trades], ["buy", "sell"])
        self.assertEqual(outcome.trades[0].quantity, 10)
        self.assertEqual(outcome.trades[1].price, Decimal("140"))
        self.assertEqual(outcome.trades[1].profit, Decimal("400.00"))
        self.assertEqual(outcome.final_value, Decimal("1400.00"))
        self.assertEqual(outcome.return_percent, Decimal("40.00"))
        self.assertEqual((outcome.closed_trades, outcome.winning_trades), (1, 1))

    def test_commission_reduces_result(self):
        outcome = simulate(
            rules(commission_percent=Decimal("1")), closes(100, 100, 130, 140)
        )
        buy, sell = outcome.trades
        self.assertEqual(buy.quantity, 9)
        self.assertEqual(buy.commission, Decimal("9.00"))
        self.assertEqual(buy.cash_after, Decimal("91.00"))
        self.assertEqual(sell.commission, Decimal("12.60"))
        self.assertEqual(outcome.total_commission, Decimal("21.60"))
        self.assertEqual(outcome.final_value, Decimal("1338.40"))
        self.assertEqual(sell.profit, Decimal("338.40"))

    def test_cash_never_goes_negative(self):
        outcome = simulate(
            rules(commission_percent=Decimal("0.05")), closes(100, 99.99, 99.99)
        )
        self.assertGreaterEqual(outcome.trades[0].cash_after, 0)

    def test_only_one_position_at_a_time(self):
        outcome = simulate(rules(), closes(90, 80, 70, 60, 50))
        self.assertEqual(len(outcome.trades), 1)

    def test_open_position_is_valued_at_last_price(self):
        outcome = simulate(rules(), closes(100, 100, 110))
        self.assertEqual(outcome.open_quantity, 10)
        self.assertEqual(outcome.final_value, Decimal("1100.00"))
        self.assertEqual(outcome.closed_trades, 0)

    def test_stop_loss_has_priority(self):
        outcome = simulate(
            rules(
                stop_loss_percent=Decimal("10"),
                sell_condition=SellCondition.TAKE_PROFIT,
                sell_value=Decimal("50"),
            ),
            closes(100, 100, 85, 80),
        )
        self.assertIn("Стоп-лосс", outcome.trades[1].reason)
        self.assertEqual(outcome.trades[1].price, Decimal("80"))
        self.assertEqual(outcome.winning_trades, 0)

    def test_take_profit_uses_entry_price(self):
        outcome = simulate(
            rules(sell_condition=SellCondition.TAKE_PROFIT, sell_value=Decimal("10")),
            closes(100, 100, 109, 111, 115),
        )
        self.assertEqual(outcome.trades[1].date, START + timedelta(days=4))

    def test_drop_from_high(self):
        outcome = simulate(
            rules(
                buy_condition=BuyCondition.DROP_FROM_HIGH,
                buy_value=Decimal("10"),
                lookback_days=3,
                sell_value=Decimal("1000"),
            ),
            closes(100, 95, 91, 85, 88),
        )
        self.assertEqual(outcome.trades[0].signal_date, START + timedelta(days=3))
        self.assertIn("максимума 95", outcome.trades[0].reason)

    def test_drop_ignores_high_outside_of_window(self):
        outcome = simulate(
            rules(
                buy_condition=BuyCondition.DROP_FROM_HIGH,
                buy_value=Decimal("10"),
                lookback_days=3,
                sell_value=Decimal("1000"),
            ),
            closes(100, 95, 91, 89, 88),
        )
        self.assertEqual(outcome.trades, [])

    def test_sma_cross_signals(self):
        outcome = simulate(
            rules(
                buy_condition=BuyCondition.SMA_CROSS_UP,
                buy_value=None,
                sell_condition=SellCondition.SMA_CROSS_DOWN,
                sell_value=None,
            ),
            closes(100, 90, 80, 90, 110, 120, 100, 80, 70, 60),
        )
        self.assertEqual([t.side for t in outcome.trades], ["buy", "sell"])
        self.assertIn("снизу вверх", outcome.trades[0].reason)
        self.assertIn("сверху вниз", outcome.trades[1].reason)

    def test_warm_up_days_are_used_for_indicators_only(self):
        data = closes(100, 90, 80, 90, 110, 120, 130)
        strategy = rules(
            buy_condition=BuyCondition.SMA_CROSS_UP,
            buy_value=None,
            sell_value=Decimal("1000"),
        )
        outcome = simulate(strategy, data, start=4)
        self.assertEqual(outcome.period_start, START + timedelta(days=4))
        self.assertEqual(outcome.buy_hold_percent, Decimal("18.18"))
        self.assertEqual(len(outcome.equity), 3)

    def test_too_small_capital_skips_signal(self):
        outcome = simulate(rules(initial_capital=Decimal("50")), closes(100, 100, 100))
        self.assertEqual(outcome.trades, [])
        self.assertEqual(outcome.skipped_signals, 2)

    def test_not_enough_data(self):
        with self.assertRaises(SimulationError):
            simulate(rules(), closes(100))
        with self.assertRaises(SimulationError):
            simulate(rules(), closes(100, 100), start=1)

    def test_loss_and_buy_hold(self):
        outcome = simulate(
            rules(stop_loss_percent=Decimal("5")), closes(100, 100, 90, 80)
        )
        self.assertEqual(outcome.return_percent, Decimal("-20.00"))
        self.assertEqual(outcome.buy_hold_percent, Decimal("-20.00"))
        self.assertEqual(outcome.max_drawdown_percent, Decimal("20.00"))

    def test_max_drawdown(self):
        values = [Decimal(v) for v in (100, 120, 90, 110, 60, 130)]
        self.assertEqual(max_drawdown(values), Decimal("50.00"))

    def test_sma(self):
        prices = [Decimal(v) for v in (1, 2, 3, 4)]
        self.assertIsNone(sma(prices, 1, 3))
        self.assertEqual(sma(prices, 3, 2), Decimal("3.5"))


def form_data(share, **kwargs):
    data = {
        "name": "Тест",
        "share": share.id,
        "initial_capital": "100000",
        "commission_percent": "0.05",
        "buy_condition": BuyCondition.PRICE_BELOW,
        "buy_value": "100",
        "sell_condition": SellCondition.PRICE_ABOVE,
        "sell_value": "120",
        "lookback_days": "20",
        "sma_short": "10",
        "sma_long": "30",
        "auto_update": "on",
    }
    return {**data, **kwargs}


class StrategyFormTests(TestCase):
    def setUp(self):
        self.share = make_share("SBER")

    def errors(self, **kwargs):
        return StrategyForm(form_data(self.share, **kwargs)).errors

    def test_valid(self):
        self.assertEqual(self.errors(), {})

    def test_value_is_required_for_threshold_conditions(self):
        self.assertIn("buy_value", self.errors(buy_value=""))
        self.assertIn("sell_value", self.errors(sell_value=""))

    def test_value_is_not_required_for_sma(self):
        errors = self.errors(
            buy_condition=BuyCondition.SMA_CROSS_UP,
            buy_value="",
            sell_condition=SellCondition.SMA_CROSS_DOWN,
            sell_value="",
        )
        self.assertEqual(errors, {})

    def test_short_average_must_be_shorter(self):
        self.assertIn("sma_short", self.errors(sma_short="30", sma_long="30"))

    def test_dates_order(self):
        errors = self.errors(date_from="2026-02-01", date_to="2026-01-01")
        self.assertIn("__all__", errors)

    def test_invalid_numbers(self):
        for field, value in (
            ("initial_capital", "0"),
            ("initial_capital", "-5"),
            ("commission_percent", "11"),
            ("buy_value", "-1"),
            ("stop_loss_percent", "100"),
        ):
            self.assertIn(field, self.errors(**{field: value}), (field, value))

    def test_owner_cannot_be_set_through_form(self):
        self.assertNotIn("owner", StrategyForm().fields)


class ViewTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("own@test.local")
        self.other = User.objects.create_user("other@test.local")
        self.share = make_share("SBER")
        for index, price in enumerate((100, 100, 130, 140)):
            add_daily(self.share, START + timedelta(days=index), price)
        self.strategy = self.make_strategy(self.user)
        self.client.force_login(self.user)

    def make_strategy(self, owner, **kwargs):
        defaults = {
            "owner": owner,
            "name": f"Стратегия {owner.username}",
            "share": self.share,
            "initial_capital": Decimal("1000"),
            "commission_percent": Decimal("0"),
            "buy_condition": BuyCondition.PRICE_BELOW,
            "buy_value": Decimal("100"),
            "sell_condition": SellCondition.PRICE_ABOVE,
            "sell_value": Decimal("120"),
        }
        return Strategy.objects.create(**{**defaults, **kwargs})

    def url(self, name, strategy=None):
        return reverse(f"strategies:{name}", args=[(strategy or self.strategy).pk])


class OwnershipTests(ViewTestCase):
    def setUp(self):
        super().setUp()
        self.foreign = self.make_strategy(self.other, name="Чужая секретная")
        run_simulation(self.foreign)

    def test_foreign_strategy_is_not_listed(self):
        response = self.client.get(reverse("strategies:list"))
        self.assertContains(response, self.strategy.name)
        self.assertNotContains(response, "Чужая секретная")

    def test_foreign_strategy_pages_give_404(self):
        for name in ("detail", "update", "delete"):
            response = self.client.get(self.url(name, self.foreign))
            self.assertEqual(response.status_code, 404, name)

    def test_foreign_strategy_cannot_be_changed(self):
        for name in ("update", "delete", "run"):
            response = self.client.post(
                self.url(name, self.foreign), form_data(self.share, name="Взлом")
            )
            self.assertEqual(response.status_code, 404, name)
        self.foreign.refresh_from_db()
        self.assertEqual(self.foreign.name, "Чужая секретная")
        self.assertTrue(SimulationResult.objects.filter(strategy=self.foreign).exists())

    def test_owner_in_post_data_is_ignored(self):
        self.client.post(
            reverse("strategies:create"),
            form_data(self.share, name="Новая", owner=self.other.id),
        )
        self.assertEqual(Strategy.objects.get(name="Новая").owner, self.user)

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        index = reverse("dashboard:index")
        urls = [
            reverse("strategies:list"),
            reverse("strategies:create"),
            self.url("detail"),
            self.url("update"),
            self.url("delete"),
        ]
        for url in urls:
            self.assertRedirects(self.client.get(url), index)
        self.assertRedirects(self.client.post(self.url("run")), index)
        self.assertFalse(SimulationResult.objects.filter(strategy=self.strategy).exists())

    def test_navigation_link_is_shown_only_after_login(self):
        link = reverse("strategies:list")
        self.assertContains(self.client.get(reverse("dashboard:index")), link)
        self.client.logout()
        self.assertNotContains(self.client.get(reverse("dashboard:index")), link)


class SimulationFlowTests(ViewTestCase):
    def test_create_strategy(self):
        response = self.client.post(
            reverse("strategies:create"), form_data(self.share, name="Новая")
        )
        strategy = Strategy.objects.get(name="Новая")
        self.assertRedirects(response, self.url("detail", strategy))

    def test_form_pages_render(self):
        self.assertEqual(self.client.get(reverse("strategies:create")).status_code, 200)
        self.assertEqual(self.client.get(self.url("update")).status_code, 200)

    def test_run_saves_journal_and_shows_result(self):
        response = self.client.post(self.url("run"), follow=True)
        self.assertContains(response, "Журнал операций")
        self.assertContains(response, "Покупка")
        self.assertContains(response, "1400,00")
        self.assertContains(response, "plotly-graph-div", count=2)
        self.assertEqual(VirtualTrade.objects.count(), 2)

    def test_run_requires_post(self):
        self.assertEqual(self.client.get(self.url("run")).status_code, 405)

    def test_repeated_run_replaces_result(self):
        self.client.post(self.url("run"))
        self.client.post(self.url("run"))
        self.assertEqual(SimulationResult.objects.count(), 1)
        self.assertEqual(VirtualTrade.objects.count(), 2)

    def test_changed_conditions_clear_result(self):
        self.client.post(self.url("run"))
        data = form_data(self.share, name="Имя", sell_value="125")
        self.client.post(self.url("update"), data)
        self.assertFalse(SimulationResult.objects.exists())

    def test_renaming_keeps_result(self):
        self.client.post(self.url("run"))
        self.strategy.refresh_from_db()
        data = form_data(
            self.share,
            name="Другое имя",
            initial_capital=self.strategy.initial_capital,
            commission_percent=self.strategy.commission_percent,
            buy_value=self.strategy.buy_value,
            sell_value=self.strategy.sell_value,
        )
        self.client.post(self.url("update"), data)
        self.assertTrue(SimulationResult.objects.exists())

    def test_no_history_shows_message(self):
        PriceRecord.objects.all().delete()
        response = self.client.post(self.url("run"), follow=True)
        self.assertContains(response, "минимум два дня")
        self.assertFalse(SimulationResult.objects.exists())

    def test_no_trades_is_reported(self):
        self.strategy.buy_value = Decimal("1")
        self.strategy.save()
        response = self.client.post(self.url("run"), follow=True)
        self.assertContains(response, "условия покупки не выполнялись")

    def test_quotes_are_not_used(self):
        PriceRecord.objects.create(
            share=self.share,
            kind=PriceRecord.Kind.QUOTE,
            recorded_at=PriceRecord.objects.first().recorded_at,
            price=1.0,
        )
        closes_list, _ = load_closes(self.strategy)
        self.assertEqual(len(closes_list), 4)
        self.assertNotIn(Decimal("1.0"), [price for _, price in closes_list])

    def test_period_limits_simulation(self):
        self.strategy.date_from = START + timedelta(days=1)
        self.strategy.date_to = START + timedelta(days=2)
        self.strategy.save()
        result = run_simulation(self.strategy)
        self.assertEqual(result.period_start, START + timedelta(days=1))
        self.assertEqual(result.period_end, START + timedelta(days=2))

    def test_delete_removes_journal(self):
        run_simulation(self.strategy)
        response = self.client.post(self.url("delete"))
        self.assertRedirects(response, reverse("strategies:list"))
        self.assertFalse(VirtualTrade.objects.exists())

    def test_share_with_strategy_can_be_deleted(self):
        run_simulation(self.strategy)
        response = self.client.post(reverse("dashboard:delete", args=[self.share.id]))
        self.assertRedirects(response, reverse("dashboard:index"))
        self.assertFalse(Share.objects.exists())
        self.assertFalse(Strategy.objects.exists())


class AutoUpdateTests(ViewTestCase):
    def test_nightly_task_updates_only_enabled_strategies(self):
        disabled = self.make_strategy(self.other, auto_update=False)
        update_strategies()
        self.assertTrue(SimulationResult.objects.filter(strategy=self.strategy).exists())
        self.assertFalse(SimulationResult.objects.filter(strategy=disabled).exists())

    def test_strategy_without_data_does_not_stop_others(self):
        empty_share = make_share("EMPTY")
        self.make_strategy(self.other, share=empty_share)
        with self.assertLogs("strategies.services", level="WARNING"):
            self.assertEqual(update_auto_strategies(), 1)

    def test_new_history_changes_result(self):
        first = run_simulation(self.strategy)
        add_daily(self.share, START + timedelta(days=4), 150)
        update_auto_strategies()
        self.assertEqual(SimulationResult.objects.count(), 1)
        latest = SimulationResult.objects.get()
        self.assertEqual(latest.final_value, first.final_value)
        self.assertEqual(latest.period_end, START + timedelta(days=4))
