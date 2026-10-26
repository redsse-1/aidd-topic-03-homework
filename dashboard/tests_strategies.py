from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from dashboard.models import (
    InvestmentStrategy,
    Share,
    SharePriceHistory,
    SimulatedTrade,
)
from dashboard.services.strategy_simulator import NoPriceHistoryError, run_strategy


class StrategySimulatorTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            "owner@example.com", "owner@example.com", "long-test-password"
        )
        self.other_user = user_model.objects.create_user(
            "other@example.com", "other@example.com", "long-test-password"
        )
        self.share = Share.objects.create(
            figi="MOEX:TQBR:SBER",
            isin="RU0009029540",
            name="Сбербанк",
            ticker="SBER",
            currency="rub",
            uid="MOEX:TQBR:SBER",
        )
        self.strategy = InvestmentStrategy.objects.create(
            owner=self.owner,
            share=self.share,
            name="Buy low sell high",
            initial_cash=Decimal("1000.00"),
            quantity=10,
            buy_below=Decimal("90"),
            sell_at_or_above=Decimal("110"),
        )

    def add_prices(self):
        today = timezone.localdate()
        SharePriceHistory.objects.bulk_create(
            [
                SharePriceHistory(
                    share=self.share,
                    date=today - timedelta(days=3),
                    close=Decimal("100"),
                ),
                SharePriceHistory(
                    share=self.share,
                    date=today - timedelta(days=2),
                    close=Decimal("80"),
                ),
                SharePriceHistory(
                    share=self.share,
                    date=today - timedelta(days=1),
                    close=Decimal("120"),
                ),
                SharePriceHistory(
                    share=self.share, date=today, close=Decimal("90")
                ),
            ]
        )

    def test_simulation_journals_virtual_operations_and_performance(self):
        self.add_prices()

        result = run_strategy(self.strategy.pk)

        self.assertEqual(
            list(result.trades.values_list("side", "price", "quantity")),
            [
                (SimulatedTrade.Side.BUY, Decimal("80"), 10),
                (SimulatedTrade.Side.SELL, Decimal("120"), 10),
                (SimulatedTrade.Side.BUY, Decimal("90"), 10),
            ],
        )
        self.assertEqual(result.ending_cash, Decimal("500.00"))
        self.assertEqual(result.ending_equity, Decimal("1400.00"))
        self.assertEqual(result.return_percent, Decimal("40.0000"))
        self.assertEqual(result.open_quantity, 10)
        self.assertEqual(result.simulated_until, timezone.localdate())

    def test_rerunning_simulation_replaces_journal_without_duplicates(self):
        self.add_prices()

        run_strategy(self.strategy.pk)
        run_strategy(self.strategy.pk)

        self.assertEqual(self.strategy.trades.count(), 3)
        self.assertEqual(
            self.strategy.trades.values("date").distinct().count(), 3
        )

    def test_simulation_requires_price_history(self):
        with self.assertRaisesMessage(
            NoPriceHistoryError, "Для акции ещё нет истории дневных цен."
        ):
            run_strategy(self.strategy.pk)

    def test_owner_can_run_strategy_from_detail_page(self):
        self.add_prices()
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("dashboard:strategy-run", args=[self.strategy.pk])
        )

        self.assertRedirects(
            response, reverse("dashboard:strategy-detail", args=[self.strategy.pk])
        )
        detail = self.client.get(
            reverse("dashboard:strategy-detail", args=[self.strategy.pk])
        )
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "40.0000%")
        self.assertContains(detail, "Покупка")

    def test_strategy_pages_are_private_to_the_owner(self):
        self.client.force_login(self.other_user)

        self.assertEqual(
            self.client.get(reverse("dashboard:strategy-list"))
            .context["strategies"]
            .count(),
            0,
        )
        self.assertEqual(
            self.client.get(
                reverse("dashboard:strategy-detail", args=[self.strategy.pk])
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse("dashboard:strategy-update", args=[self.strategy.pk])
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("dashboard:strategy-run", args=[self.strategy.pk])
            ).status_code,
            404,
        )

    def test_owner_can_create_strategy(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("dashboard:strategy-create"),
            {
                "name": "Second strategy",
                "share": self.share.pk,
                "initial_cash": "500.00",
                "quantity": 2,
                "buy_below": "50",
                "sell_at_or_above": "75",
            },
        )

        self.assertEqual(response.status_code, 302)
        strategy = InvestmentStrategy.objects.get(name="Second strategy")
        self.assertEqual(strategy.owner, self.owner)

    def test_strategy_rejects_sell_threshold_not_above_buy_threshold(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("dashboard:strategy-create"),
            {
                "name": "Invalid thresholds",
                "share": self.share.pk,
                "initial_cash": "500.00",
                "quantity": 2,
                "buy_below": "75",
                "sell_at_or_above": "75",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("sell_at_or_above", response.context["form"].errors)
        self.assertFalse(
            InvestmentStrategy.objects.filter(name="Invalid thresholds").exists()
        )
