from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from dashboard.models import (
    InvestmentPortfolio,
    PortfolioPosition,
    PortfolioTransaction,
    Share,
)
from dashboard.services.portfolio import (
    PortfolioOperationError,
    execute_portfolio_transaction,
)


class VirtualPortfolioTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            "portfolio@example.com",
            "portfolio@example.com",
            "long-test-password",
        )
        self.other_user = user_model.objects.create_user(
            "other-portfolio@example.com",
            "other-portfolio@example.com",
            "long-test-password",
        )
        self.share = Share.objects.create(
            figi="MOEX:TQBR:SBER",
            isin="RU0009029540",
            name="Сбербанк",
            ticker="SBER",
            currency="rub",
            uid="MOEX:TQBR:SBER",
            last_price=Decimal("100"),
        )
        self.portfolio = InvestmentPortfolio.objects.create(
            owner=self.owner, name="Долгосрочный"
        )

    def trade(self, side, quantity, share=None):
        return execute_portfolio_transaction(
            portfolio_id=self.portfolio.pk,
            owner_id=self.owner.pk,
            share_id=(share or self.share).pk,
            side=side,
            quantity=Decimal(quantity),
        )

    def test_buys_update_weighted_average_and_sell_realizes_profit(self):
        self.trade(PortfolioTransaction.Side.BUY, "10")
        self.share.last_price = Decimal("130")
        self.share.save(update_fields=("last_price",))
        self.trade(PortfolioTransaction.Side.BUY, "5")

        position = PortfolioPosition.objects.get(
            portfolio=self.portfolio, share=self.share
        )
        self.assertEqual(position.quantity, Decimal("15"))
        self.assertEqual(position.average_cost, Decimal("110"))

        self.share.last_price = Decimal("150")
        self.share.save(update_fields=("last_price",))
        sell = self.trade(PortfolioTransaction.Side.SELL, "6")
        position.refresh_from_db()

        self.assertEqual(position.quantity, Decimal("9"))
        self.assertEqual(position.average_cost, Decimal("110"))
        self.assertEqual(position.realized_profit, Decimal("240.00"))
        self.assertEqual(sell.realized_profit, Decimal("240.00"))
        self.assertEqual(sell.price, Decimal("150"))
        self.assertEqual(sell.amount, Decimal("900.00"))

    def test_sale_cannot_exceed_position_and_does_not_create_transaction(self):
        self.trade(PortfolioTransaction.Side.BUY, "2")

        with self.assertRaisesMessage(
            PortfolioOperationError, "Нельзя продать больше"
        ):
            self.trade(PortfolioTransaction.Side.SELL, "3")

        self.assertEqual(self.portfolio.transactions.count(), 1)
        self.assertEqual(
            PortfolioPosition.objects.get(portfolio=self.portfolio).quantity,
            Decimal("2"),
        )

    def test_operation_requires_a_current_share_price(self):
        self.share.last_price = None
        self.share.save(update_fields=("last_price",))

        with self.assertRaisesMessage(
            PortfolioOperationError, "нет актуальной цены"
        ):
            self.trade(PortfolioTransaction.Side.BUY, "1")

        self.assertFalse(PortfolioPosition.objects.exists())
        self.assertFalse(PortfolioTransaction.objects.exists())

    def test_operation_rejects_nonpositive_quantity(self):
        with self.assertRaisesMessage(PortfolioOperationError, "больше нуля"):
            self.trade(PortfolioTransaction.Side.BUY, "0")

        self.assertFalse(PortfolioTransaction.objects.exists())

    def test_portfolio_pages_show_valuation_and_are_private(self):
        self.trade(PortfolioTransaction.Side.BUY, "10")
        self.share.last_price = Decimal("120")
        self.share.save(update_fields=("last_price",))
        self.client.force_login(self.owner)

        detail = self.client.get(
            reverse("dashboard:portfolio-detail", args=[self.portfolio.pk])
        )
        self.assertEqual(detail.status_code, 200)
        summary = detail.context["currency_summaries"][0]
        self.assertEqual(summary["market_value"], Decimal("1200.00"))
        self.assertEqual(summary["realized_profit"], Decimal("0.00"))
        self.assertEqual(summary["unrealized_profit"], Decimal("200.00"))
        self.assertContains(detail, "История операций")

        self.client.force_login(self.other_user)
        self.assertEqual(
            self.client.get(reverse("dashboard:portfolio-list"))
            .context["portfolios"]
            .count(),
            0,
        )
        self.assertEqual(
            self.client.get(
                reverse("dashboard:portfolio-detail", args=[self.portfolio.pk])
            ).status_code,
            404,
        )

    def test_portfolio_valuation_is_unavailable_without_a_positive_price(self):
        self.trade(PortfolioTransaction.Side.BUY, "1")
        self.share.last_price = Decimal("0")
        self.share.save(update_fields=("last_price",))
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("dashboard:portfolio-detail", args=[self.portfolio.pk])
        )

        summary = response.context["currency_summaries"][0]
        self.assertFalse(summary["value_available"])
        self.assertIsNone(summary["market_value"])
        self.assertFalse(summary["unrealized_available"])
        self.assertIsNone(summary["unrealized_profit"])

    def test_owner_can_create_portfolio_and_buy_from_the_page(self):
        self.client.force_login(self.owner)
        create = self.client.post(
            reverse("dashboard:portfolio-list"), {"name": "Новый"}
        )
        portfolio = InvestmentPortfolio.objects.get(name="Новый")
        self.assertEqual(portfolio.owner, self.owner)
        self.assertEqual(create.status_code, 302)

        response = self.client.post(
            reverse("dashboard:portfolio-detail", args=[portfolio.pk]),
            {
                "side": PortfolioTransaction.Side.BUY,
                "share": self.share.pk,
                "quantity": "2",
            },
        )
        self.assertEqual(response.status_code, 302)
        transaction = PortfolioTransaction.objects.get(portfolio=portfolio)
        self.assertEqual(transaction.price, Decimal("100"))
        self.assertEqual(transaction.amount, Decimal("200.00"))

    def test_sell_validation_error_is_shown_on_portfolio_page(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("dashboard:portfolio-detail", args=[self.portfolio.pk]),
            {
                "side": PortfolioTransaction.Side.SELL,
                "share": self.share.pk,
                "quantity": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Нельзя продать больше", str(response.context["transaction_form"].errors))
        self.assertFalse(PortfolioTransaction.objects.exists())
