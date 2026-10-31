from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from dashboard.models import Share
from dashboard.test_market_data import make_share
from portfolios.forms import MAX_QUANTITY, OperationForm, PortfolioForm
from portfolios.models import Operation, Portfolio, Position
from portfolios.services import OperationError, execute_operation, summarize

User = get_user_model()
BUY = Operation.Side.BUY
SELL = Operation.Side.SELL


class PortfolioTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("own@test.local")
        self.other = User.objects.create_user("other@test.local")
        self.share = make_share("SBER", last_price=100.0)
        self.portfolio = Portfolio.objects.create(owner=self.user, name="Основной")

    def set_price(self, price, share=None):
        Share.objects.filter(pk=(share or self.share).pk).update(last_price=price)

    def trade(self, side, quantity, price=None, share=None):
        if price is not None:
            self.set_price(price, share)
        return execute_operation(self.portfolio, share or self.share, side, quantity)

    def position(self, share=None):
        return Position.objects.get(portfolio=self.portfolio, share=share or self.share)

    def summary(self):
        positions = list(self.portfolio.positions.select_related("share"))
        return summarize(positions)


class AverageAndProfitTests(PortfolioTestCase):
    def test_first_buy(self):
        operation = self.trade(BUY, 10)
        position = self.position()
        self.assertEqual(position.quantity, 10)
        self.assertEqual(position.average_price, Decimal("100"))
        self.assertEqual(operation.price, Decimal("100"))
        self.assertEqual(operation.amount, Decimal("1000.00"))
        self.assertIsNone(operation.realized_profit)

    def test_average_is_weighted_by_quantity(self):
        self.trade(BUY, 10, 100)
        self.trade(BUY, 30, 200)
        self.assertEqual(self.position().quantity, 40)
        self.assertEqual(self.position().average_price, Decimal("175"))

    def test_average_keeps_fractions(self):
        self.trade(BUY, 1, 100)
        self.trade(BUY, 2, 100.01)
        self.assertEqual(self.position().average_price, Decimal("100.00666667"))

    def test_sell_keeps_average_and_records_profit(self):
        self.trade(BUY, 10, 100)
        self.trade(BUY, 10, 200)
        operation = self.trade(SELL, 5, 300)
        position = self.position()
        self.assertEqual(position.average_price, Decimal("150"))
        self.assertEqual(position.quantity, 15)
        self.assertEqual(operation.realized_profit, Decimal("750.00"))
        self.assertEqual(position.realized_profit, Decimal("750.00"))

    def test_sell_with_loss(self):
        self.trade(BUY, 10, 100)
        operation = self.trade(SELL, 4, 90)
        self.assertEqual(operation.realized_profit, Decimal("-40.00"))

    def test_realized_profit_accumulates(self):
        self.trade(BUY, 10, 100)
        self.trade(SELL, 3, 110)
        self.trade(SELL, 3, 90)
        self.assertEqual(self.position().realized_profit, Decimal("0.00"))

    def test_full_close_keeps_profit_and_resets_average(self):
        self.trade(BUY, 10, 100)
        self.trade(SELL, 10, 120)
        position = self.position()
        self.assertEqual(position.quantity, 0)
        self.assertEqual(position.average_price, 0)
        self.assertEqual(position.realized_profit, Decimal("200.00"))

    def test_buy_after_full_close_starts_new_average(self):
        self.trade(BUY, 10, 100)
        self.trade(SELL, 10, 120)
        self.trade(BUY, 5, 50)
        position = self.position()
        self.assertEqual(position.average_price, Decimal("50"))
        self.assertEqual(position.realized_profit, Decimal("200.00"))

    def test_position_matches_replay_of_operations(self):
        for side, quantity, price in (
            (BUY, 7, 101.13),
            (BUY, 13, 99.37),
            (SELL, 5, 104.71),
            (BUY, 3, 97.01),
            (SELL, 18, 88.88),
            (BUY, 4, 90.5),
        ):
            self.trade(side, quantity, price)

        quantity, cost, realized = 0, Decimal("0"), Decimal("0")
        for operation in self.portfolio.operations.order_by("id"):
            if operation.side == BUY:
                quantity += operation.quantity
                cost += operation.price * operation.quantity
            else:
                average = cost / quantity
                realized += (operation.price - average) * operation.quantity
                cost -= average * operation.quantity
                quantity -= operation.quantity

        position = self.position()
        self.assertEqual(position.quantity, quantity)
        self.assertAlmostEqual(position.average_price, cost / quantity, places=6)
        self.assertAlmostEqual(position.realized_profit, realized, delta=Decimal("0.03"))


class ChecksTests(PortfolioTestCase):
    def test_cannot_sell_more_than_held(self):
        self.trade(BUY, 5)
        with self.assertRaisesRegex(OperationError, "в портфеле 5 шт"):
            self.trade(SELL, 6)
        self.assertEqual(self.position().quantity, 5)
        self.assertEqual(self.portfolio.operations.count(), 1)

    def test_cannot_sell_without_position(self):
        with self.assertRaisesRegex(OperationError, "в портфеле 0 шт"):
            self.trade(SELL, 1)
        self.assertFalse(Position.objects.exists())

    def test_cannot_sell_from_closed_position(self):
        self.trade(BUY, 5)
        self.trade(SELL, 5)
        with self.assertRaises(OperationError):
            self.trade(SELL, 1)

    def test_quantity_must_be_positive(self):
        for quantity in (0, -1):
            with self.assertRaisesRegex(OperationError, "положительным"):
                self.trade(BUY, quantity)
        self.assertFalse(Operation.objects.exists())

    def test_share_without_price(self):
        self.set_price(None)
        for side in (BUY, SELL):
            with self.assertRaisesRegex(OperationError, "нет текущей цены"):
                self.trade(side, 1)
        self.assertFalse(Operation.objects.exists())
        self.assertFalse(Position.objects.exists())

    def test_zero_price_is_rejected(self):
        self.set_price(0.0)
        with self.assertRaises(OperationError):
            self.trade(BUY, 1)

    def test_price_is_read_from_database(self):
        stale_share = Share.objects.get(pk=self.share.pk)
        self.set_price(250.0)
        operation = execute_operation(self.portfolio, stale_share, BUY, 1)
        self.assertEqual(operation.price, Decimal("250"))

    def test_positions_of_portfolios_are_separate(self):
        second = Portfolio.objects.create(owner=self.user, name="Второй")
        self.trade(BUY, 5)
        with self.assertRaises(OperationError):
            execute_operation(second, self.share, SELL, 1)

    def test_form_limits_quantity(self):
        for value in ("0", "-3", "1.5", "abc", "", str(MAX_QUANTITY + 1)):
            form = OperationForm(
                {"side": BUY, "share": self.share.pk, "quantity": value}
            )
            self.assertIn("quantity", form.errors, value)

    def test_portfolio_name_is_unique_for_owner(self):
        self.assertFalse(PortfolioForm({"name": "Основной"}, owner=self.user).is_valid())
        self.assertTrue(PortfolioForm({"name": "Основной"}, owner=self.other).is_valid())


class SummaryTests(PortfolioTestCase):
    def test_empty_portfolio(self):
        summary = self.summary()
        self.assertEqual(summary.market_value, 0)
        self.assertIsNone(summary.unrealized_percent)

    def test_value_and_unrealized_profit(self):
        self.trade(BUY, 10, 100)
        self.set_price(125)
        summary = self.summary()
        self.assertEqual(summary.cost, Decimal("1000.00"))
        self.assertEqual(summary.market_value, Decimal("1250.00"))
        self.assertEqual(summary.unrealized, Decimal("250.00"))
        self.assertEqual(summary.unrealized_percent, Decimal("25.00"))
        self.assertEqual(summary.realized, 0)

    def test_realized_and_unrealized_are_separate(self):
        self.trade(BUY, 10, 100)
        self.trade(SELL, 4, 150)
        self.set_price(90)
        summary = self.summary()
        self.assertEqual(summary.realized, Decimal("200.00"))
        self.assertEqual(summary.unrealized, Decimal("-60.00"))
        self.assertEqual(summary.total_profit, Decimal("140.00"))

    def test_several_positions_and_closed_one(self):
        gazp = make_share("GAZP", last_price=50.0)
        lkoh = make_share("LKOH", last_price=10.0)
        self.trade(BUY, 2, 100)
        self.trade(BUY, 10, share=gazp)
        self.trade(BUY, 1, share=lkoh)
        self.trade(SELL, 1, 20, share=lkoh)

        summary = self.summary()

        self.assertEqual(summary.market_value, Decimal("700.00"))
        self.assertEqual(summary.realized, Decimal("10.00"))
        self.assertEqual([row.position.share.ticker for row in summary.rows], ["GAZP", "SBER"])
        self.assertEqual([position.share.ticker for position in summary.closed], ["LKOH"])

    def test_position_without_price_is_excluded_and_reported(self):
        gazp = make_share("GAZP", last_price=50.0)
        self.trade(BUY, 2, 100)
        self.trade(BUY, 2, share=gazp)
        self.set_price(None, gazp)
        summary = self.summary()
        self.assertEqual(summary.market_value, Decimal("200.00"))
        self.assertEqual(summary.cost, Decimal("200.00"))
        self.assertEqual(summary.unpriced, 1)


class OwnershipTests(PortfolioTestCase):
    def setUp(self):
        super().setUp()
        self.trade(BUY, 5)
        self.client.force_login(self.other)

    def url(self, name):
        return reverse(f"portfolios:{name}", args=[self.portfolio.pk])

    def test_foreign_portfolio_is_not_listed(self):
        Portfolio.objects.create(owner=self.other, name="Свой")
        response = self.client.get(reverse("portfolios:list"))
        self.assertContains(response, "Свой")
        self.assertNotContains(response, "Основной")

    def test_foreign_pages_give_404(self):
        for name in ("detail", "update", "delete", "trade", "history"):
            self.assertEqual(self.client.get(self.url(name)).status_code, 404, name)

    def test_foreign_portfolio_cannot_be_changed(self):
        data = {"name": "Взлом", "side": SELL, "share": self.share.pk, "quantity": 5}
        for name in ("update", "delete", "trade"):
            self.assertEqual(self.client.post(self.url(name), data).status_code, 404, name)
        self.portfolio.refresh_from_db()
        self.assertEqual(self.portfolio.name, "Основной")
        self.assertEqual(self.position().quantity, 5)

    def test_owner_in_post_data_is_ignored(self):
        self.client.post(
            reverse("portfolios:create"), {"name": "Новый", "owner": self.user.pk}
        )
        self.assertEqual(Portfolio.objects.get(name="Новый").owner, self.other)

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        index = reverse("dashboard:index")
        pages = [reverse("portfolios:list"), reverse("portfolios:create")]
        pages += [self.url(name) for name in ("detail", "trade", "history")]
        for url in pages:
            self.assertRedirects(self.client.get(url), index)
        data = {"side": SELL, "share": self.share.pk, "quantity": 5}
        self.assertRedirects(self.client.post(self.url("trade"), data), index)
        self.assertEqual(self.position().quantity, 5)


class FlowTests(PortfolioTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.trade_url = reverse("portfolios:trade", args=[self.portfolio.pk])
        self.detail_url = reverse("portfolios:detail", args=[self.portfolio.pk])

    def post(self, side, quantity, **extra):
        data = {"side": side, "share": self.share.pk, "quantity": quantity, **extra}
        return self.client.post(self.trade_url, data)

    def test_create_rename_delete(self):
        self.client.post(reverse("portfolios:create"), {"name": "Новый"})
        portfolio = Portfolio.objects.get(name="Новый")
        self.client.post(
            reverse("portfolios:update", args=[portfolio.pk]), {"name": "Имя"}
        )
        portfolio.refresh_from_db()
        self.assertEqual(portfolio.name, "Имя")
        response = self.client.post(reverse("portfolios:delete", args=[portfolio.pk]))
        self.assertRedirects(response, reverse("portfolios:list"))

    def test_pages_render(self):
        for url in (
            reverse("portfolios:list"),
            reverse("portfolios:create"),
            self.detail_url,
            self.trade_url,
            reverse("portfolios:history", args=[self.portfolio.pk]),
            reverse("portfolios:update", args=[self.portfolio.pk]),
            reverse("portfolios:delete", args=[self.portfolio.pk]),
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_buy_through_form(self):
        self.assertRedirects(self.post(BUY, 3), self.detail_url)
        self.assertEqual(self.position().quantity, 3)
        self.assertContains(self.client.get(self.detail_url), "SBER")

    def test_price_in_request_is_ignored(self):
        self.post(BUY, 1, price="1")
        self.assertEqual(Operation.objects.get().price, Decimal("100"))

    def test_too_large_sale_shows_error(self):
        self.post(BUY, 2)
        response = self.post(SELL, 3)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Нельзя продать 3 шт.")
        self.assertEqual(self.position().quantity, 2)

    def test_share_without_price_shows_error(self):
        self.set_price(None)
        response = self.post(BUY, 1)
        self.assertContains(response, "нет текущей цены")

    def test_invalid_quantity_shows_form(self):
        self.assertEqual(self.post(BUY, 0).status_code, 200)
        self.assertFalse(Operation.objects.exists())

    def test_trade_form_is_prefilled(self):
        response = self.client.get(self.trade_url, {"share": self.share.pk, "side": SELL})
        form = response.context["form"]
        self.assertEqual(form.initial["side"], SELL)
        self.assertEqual(form.initial["share"], str(self.share.pk))

    def test_history_lists_operations_newest_first(self):
        self.post(BUY, 2)
        self.post(SELL, 1)
        response = self.client.get(reverse("portfolios:history", args=[self.portfolio.pk]))
        sides = [operation.side for operation in response.context["operations"]]
        self.assertEqual(sides, [SELL, BUY])

    def test_detail_shows_closed_position(self):
        self.post(BUY, 2)
        self.post(SELL, 2)
        response = self.client.get(self.detail_url)
        self.assertContains(response, "Закрытые позиции")
        self.assertContains(response, "Открытых позиций нет")

    def test_share_page_has_trade_link(self):
        url = reverse("dashboard:detail", args=[self.share.pk])
        self.assertContains(self.client.get(url), "Купить в портфель")
        self.client.logout()
        self.assertNotContains(self.client.get(url), "Купить в портфель")

    def test_navigation_is_shown_only_after_login(self):
        link = reverse("portfolios:list")
        self.assertContains(self.client.get(reverse("dashboard:index")), link)
        self.client.logout()
        self.assertNotContains(self.client.get(reverse("dashboard:index")), link)

    def test_share_with_operations_can_be_deleted(self):
        self.post(BUY, 2)
        response = self.client.post(reverse("dashboard:delete", args=[self.share.pk]))
        self.assertRedirects(response, reverse("dashboard:index"))
        self.assertFalse(Operation.objects.exists())
