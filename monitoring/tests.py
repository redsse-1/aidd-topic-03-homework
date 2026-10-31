from datetime import datetime
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from dashboard.models import Share
from dashboard.services.market_data import MarketDataError, Quote
from dashboard.tasks import update_last_price
from dashboard.test_market_data import FakeProvider, make_share
from monitoring.forms import PriceTargetForm, WatchlistForm, WatchlistItemForm
from monitoring.models import Notification, PriceTarget, Watchlist, WatchlistItem
from monitoring.services import check_price_targets

User = get_user_model()
ABOVE = PriceTarget.Direction.ABOVE
BELOW = PriceTarget.Direction.BELOW


class MonitoringTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("own@test.local")
        self.other = User.objects.create_user("other@test.local")
        self.share = make_share("SBER", last_price=90.0)
        self.watchlist = Watchlist.objects.create(owner=self.user, name="Мой")
        self.item = WatchlistItem.objects.create(
            watchlist=self.watchlist, share=self.share
        )

    def make_target(self, direction=ABOVE, price="100", **kwargs):
        return PriceTarget.objects.create(
            item=self.item, direction=direction, target_price=Decimal(price), **kwargs
        )

    def set_price(self, price):
        Share.objects.filter(pk=self.share.pk).update(last_price=price)


@override_settings(MONITORING_REARM_PERCENT=0.1)
class CheckTargetsTests(MonitoringTestCase):
    def test_nothing_happens_before_level(self):
        self.make_target()
        self.assertEqual(check_price_targets(), 0)

    def test_reaching_level_above_creates_notification(self):
        target = self.make_target()
        self.set_price(101.5)

        self.assertEqual(check_price_targets(), 1)

        notification = Notification.objects.get()
        self.assertEqual(notification.owner, self.user)
        self.assertEqual(notification.share, self.share)
        self.assertEqual(notification.price, Decimal("101.5"))
        self.assertEqual(notification.target_price, Decimal("100"))
        self.assertEqual(notification.direction, ABOVE)
        target.refresh_from_db()
        self.assertTrue(target.is_triggered)

    def test_reaching_level_below(self):
        self.make_target(BELOW, "85")
        self.set_price(85.0)
        self.assertEqual(check_price_targets(), 1)

    def test_exact_level_counts(self):
        self.make_target(ABOVE, "90")
        self.assertEqual(check_price_targets(), 1)

    def test_no_repeats_while_price_stays_beyond_level(self):
        self.make_target()
        self.set_price(101.0)
        check_price_targets()
        for price in (101.0, 105.0, 102.0, 100.0):
            self.set_price(price)
            self.assertEqual(check_price_targets(), 0)
        self.assertEqual(Notification.objects.count(), 1)

    def test_repeated_check_without_new_prices_adds_nothing(self):
        self.make_target()
        self.set_price(101.0)
        results = [check_price_targets() for _ in range(5)]
        self.assertEqual(results, [1, 0, 0, 0, 0])

    def test_new_crossing_is_a_new_event(self):
        self.make_target()
        self.set_price(101.0)
        check_price_targets()
        self.set_price(95.0)
        check_price_targets()
        self.set_price(102.0)

        self.assertEqual(check_price_targets(), 1)

        numbers = Notification.objects.order_by("event_number")
        self.assertEqual([n.event_number for n in numbers], [1, 2])

    def test_fluctuation_near_level_is_not_a_new_event(self):
        self.make_target()
        self.set_price(100.5)
        check_price_targets()
        for price in (99.95, 100.2, 99.91, 100.3):
            self.set_price(price)
            self.assertEqual(check_price_targets(), 0, price)

    def test_leaving_level_with_margin_rearms_target(self):
        self.make_target()
        self.set_price(100.5)
        check_price_targets()
        self.set_price(99.8)
        check_price_targets()
        self.set_price(100.0)
        self.assertEqual(check_price_targets(), 1)

    def test_rearm_for_level_below(self):
        self.make_target(BELOW, "85")
        self.set_price(84.0)
        check_price_targets()
        self.set_price(85.05)
        check_price_targets()
        self.set_price(84.0)
        self.assertEqual(check_price_targets(), 0)
        self.set_price(86.0)
        check_price_targets()
        self.set_price(84.0)
        self.assertEqual(check_price_targets(), 1)

    def test_inactive_target_is_skipped(self):
        self.make_target(is_active=False)
        self.set_price(120.0)
        self.assertEqual(check_price_targets(), 0)

    def test_share_without_price_is_skipped(self):
        self.make_target()
        self.set_price(None)
        self.assertEqual(check_price_targets(), 0)

    def test_several_users_get_their_own_notifications(self):
        self.make_target()
        foreign_list = Watchlist.objects.create(owner=self.other, name="Чужой")
        foreign_item = WatchlistItem.objects.create(
            watchlist=foreign_list, share=self.share
        )
        PriceTarget.objects.create(
            item=foreign_item, direction=ABOVE, target_price=Decimal("100")
        )
        self.set_price(101.0)

        self.assertEqual(check_price_targets(), 2)

        self.assertEqual(Notification.objects.filter(owner=self.user).count(), 1)
        self.assertEqual(Notification.objects.filter(owner=self.other).count(), 1)

    def test_database_rejects_duplicate_event(self):
        target = self.make_target()
        self.set_price(101.0)
        check_price_targets()
        existing = Notification.objects.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Notification.objects.create(
                owner=self.user,
                share=self.share,
                target=target,
                event_number=existing.event_number,
                direction=ABOVE,
                target_price=Decimal("100"),
                price=Decimal("101"),
            )

    def test_notification_survives_target_deletion(self):
        target = self.make_target()
        self.set_price(101.0)
        check_price_targets()
        target.delete()
        notification = Notification.objects.get()
        self.assertIsNone(notification.target)
        self.assertEqual(notification.target_price, Decimal("100"))


class PriceTaskTests(MonitoringTestCase):
    deal = timezone.make_aware(datetime(2026, 10, 30, 12, 0))

    def run_task(self, provider):
        with mock.patch("dashboard.tasks.get_provider", return_value=provider):
            update_last_price()

    def test_task_checks_targets_after_prices(self):
        self.make_target()
        self.run_task(FakeProvider(prices={"SBER": Quote(101.0, self.deal)}))
        self.assertEqual(Notification.objects.get().price, Decimal("101"))

    def test_repeated_polls_outside_trading_do_not_repeat(self):
        self.make_target()
        provider = FakeProvider(prices={"SBER": Quote(101.0)})
        for _ in range(4):
            self.run_task(provider)
        self.assertEqual(Notification.objects.count(), 1)

    def test_provider_failure_skips_check(self):
        self.make_target()
        self.set_price(101.0)
        provider = FakeProvider(error=MarketDataError("down"))
        with self.assertLogs("dashboard.tasks", level="ERROR"):
            self.run_task(provider)
        self.assertFalse(Notification.objects.exists())


class FormTests(MonitoringTestCase):
    def target_form(self, item=None, **kwargs):
        data = {"direction": ABOVE, "target_price": "100", "is_active": "on"}
        return PriceTargetForm({**data, **kwargs}, item=item or self.item)

    def test_watchlist_name_is_unique_for_owner(self):
        self.assertFalse(WatchlistForm({"name": "Мой"}, owner=self.user).is_valid())
        self.assertTrue(WatchlistForm({"name": "Мой"}, owner=self.other).is_valid())

    def test_share_cannot_be_added_twice(self):
        form = WatchlistItemForm(
            {"watchlist": self.watchlist.pk, "share": self.share.pk}, owner=self.user
        )
        self.assertFalse(form.is_valid())

    def test_foreign_watchlist_is_not_accepted(self):
        foreign = Watchlist.objects.create(owner=self.other, name="Чужой")
        form = WatchlistItemForm(
            {"watchlist": foreign.pk, "share": self.share.pk}, owner=self.user
        )
        self.assertIn("watchlist", form.errors)

    def test_target_price_must_be_positive(self):
        for value in ("0", "-5", "abc", ""):
            self.assertIn("target_price", self.target_form(target_price=value).errors)

    def test_same_level_in_another_list_is_rejected(self):
        self.make_target()
        second = Watchlist.objects.create(owner=self.user, name="Второй")
        item = WatchlistItem.objects.create(watchlist=second, share=self.share)
        self.assertIn("__all__", self.target_form(item=item).errors)

    def test_same_level_of_another_user_is_allowed(self):
        self.make_target()
        foreign = Watchlist.objects.create(owner=self.other, name="Чужой")
        item = WatchlistItem.objects.create(watchlist=foreign, share=self.share)
        self.assertTrue(self.target_form(item=item).is_valid())


class OwnershipTests(MonitoringTestCase):
    def setUp(self):
        super().setUp()
        self.target = self.make_target()
        self.set_price(101.0)
        check_price_targets()
        self.notification = Notification.objects.get()
        self.client.force_login(self.other)

    def url(self, name, *args):
        return reverse(f"monitoring:{name}", args=args)

    def test_foreign_data_is_not_listed(self):
        Watchlist.objects.create(owner=self.other, name="Свой")
        response = self.client.get(self.url("list"))
        self.assertContains(response, "Свой")
        self.assertNotContains(response, "Мой")
        response = self.client.get(self.url("notifications"))
        self.assertContains(response, "Уведомлений пока нет")

    def test_foreign_pages_give_404(self):
        urls = [
            self.url("detail", self.watchlist.pk),
            self.url("update", self.watchlist.pk),
            self.url("delete", self.watchlist.pk),
            self.url("target_add", self.item.pk),
            self.url("target_update", self.target.pk),
        ]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_foreign_data_cannot_be_changed(self):
        urls = [
            self.url("update", self.watchlist.pk),
            self.url("delete", self.watchlist.pk),
            self.url("item_delete", self.item.pk),
            self.url("target_add", self.item.pk),
            self.url("target_update", self.target.pk),
            self.url("target_delete", self.target.pk),
            self.url("notification_read", self.notification.pk),
        ]
        for url in urls:
            response = self.client.post(url, {"name": "Взлом", "target_price": "1"})
            self.assertEqual(response.status_code, 404, url)

        self.watchlist.refresh_from_db()
        self.notification.refresh_from_db()
        self.assertEqual(self.watchlist.name, "Мой")
        self.assertTrue(PriceTarget.objects.filter(pk=self.target.pk).exists())
        self.assertIsNone(self.notification.read_at)

    def test_read_all_does_not_touch_foreign_notifications(self):
        self.client.post(self.url("notifications_read_all"))
        self.notification.refresh_from_db()
        self.assertIsNone(self.notification.read_at)

    def test_cannot_add_share_to_foreign_list(self):
        share = make_share("GAZP")
        self.client.post(
            self.url("item_add"), {"watchlist": self.watchlist.pk, "share": share.pk}
        )
        self.assertFalse(WatchlistItem.objects.filter(share=share).exists())

    def test_foreign_badge_is_not_counted(self):
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.context["unread_notifications"], 0)

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        index = reverse("dashboard:index")
        for url in (
            self.url("list"),
            self.url("create"),
            self.url("detail", self.watchlist.pk),
            self.url("notifications"),
        ):
            self.assertRedirects(self.client.get(url), index)
        response = self.client.post(self.url("item_delete", self.item.pk))
        self.assertRedirects(response, index)
        self.assertTrue(WatchlistItem.objects.filter(pk=self.item.pk).exists())


class FlowTests(MonitoringTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def url(self, name, *args):
        return reverse(f"monitoring:{name}", args=args)

    def test_create_watchlist(self):
        response = self.client.post(self.url("create"), {"name": "Дивиденды"})
        watchlist = Watchlist.objects.get(name="Дивиденды")
        self.assertRedirects(response, self.url("detail", watchlist.pk))
        self.assertEqual(watchlist.owner, self.user)

    def test_rename_and_delete_watchlist(self):
        self.client.post(self.url("update", self.watchlist.pk), {"name": "Новое"})
        self.watchlist.refresh_from_db()
        self.assertEqual(self.watchlist.name, "Новое")
        response = self.client.post(self.url("delete", self.watchlist.pk))
        self.assertRedirects(response, self.url("list"))
        self.assertFalse(Watchlist.objects.exists())

    def test_form_pages_render(self):
        target = self.make_target()
        for url in (
            self.url("create"),
            self.url("update", self.watchlist.pk),
            self.url("target_add", self.item.pk),
            self.url("target_update", target.pk),
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_add_and_remove_share(self):
        share = make_share("GAZP")
        response = self.client.post(
            self.url("item_add"), {"watchlist": self.watchlist.pk, "share": share.pk}
        )
        self.assertRedirects(response, self.url("detail", self.watchlist.pk))
        item = WatchlistItem.objects.get(share=share)
        self.client.post(self.url("item_delete", item.pk))
        self.assertFalse(WatchlistItem.objects.filter(pk=item.pk).exists())

    def test_duplicate_share_shows_message(self):
        response = self.client.post(
            self.url("item_add"),
            {"watchlist": self.watchlist.pk, "share": self.share.pk},
            follow=True,
        )
        self.assertContains(response, "уже есть в списке")

    def test_target_is_shown_with_status(self):
        self.client.post(
            self.url("target_add", self.item.pk),
            {"direction": ABOVE, "target_price": "100", "is_active": "on"},
        )
        response = self.client.get(self.url("detail", self.watchlist.pk))
        self.assertContains(response, "ожидает")
        self.set_price(101.0)
        check_price_targets()
        response = self.client.get(self.url("detail", self.watchlist.pk))
        self.assertContains(response, "достигнут")

    def test_changed_target_is_tracked_again(self):
        target = self.make_target()
        self.set_price(101.0)
        check_price_targets()

        self.client.post(
            self.url("target_update", target.pk),
            {"direction": ABOVE, "target_price": "100.5", "is_active": "on"},
        )

        self.assertEqual(check_price_targets(), 1)
        self.assertEqual(Notification.objects.count(), 2)

    def test_saving_same_values_keeps_state(self):
        target = self.make_target()
        self.set_price(101.0)
        check_price_targets()
        self.client.post(
            self.url("target_update", target.pk),
            {"direction": ABOVE, "target_price": "100", "is_active": "on"},
        )
        self.assertEqual(check_price_targets(), 0)

    def test_delete_target(self):
        target = self.make_target()
        self.client.post(self.url("target_delete", target.pk))
        self.assertFalse(PriceTarget.objects.exists())

    def test_post_only_actions(self):
        target = self.make_target()
        for url in (
            self.url("target_delete", target.pk),
            self.url("item_delete", self.item.pk),
            self.url("item_add"),
            self.url("notifications_read_all"),
        ):
            self.assertEqual(self.client.get(url).status_code, 405, url)

    def test_notifications_page_and_badge(self):
        self.make_target()
        self.set_price(101.0)
        check_price_targets()

        response = self.client.get(self.url("notifications"))
        self.assertContains(response, "SBER")
        self.assertContains(response, "Цена поднялась до уровня")
        self.assertContains(response, "Уведомления (1)")

        notification = Notification.objects.get()
        self.client.post(self.url("notification_read", notification.pk))
        notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)
        response = self.client.get(self.url("notifications"))
        self.assertNotContains(response, "Уведомления (1)")

    def test_read_all(self):
        self.make_target("above", "80")
        self.make_target("above", "85")
        check_price_targets()
        self.client.post(self.url("notifications_read_all"))
        self.assertFalse(Notification.objects.filter(read_at__isnull=True).exists())

    def test_share_page_has_watch_form(self):
        url = reverse("dashboard:detail", args=[self.share.pk])
        self.assertContains(self.client.get(url), "Добавить в список наблюдения")

    def test_share_page_for_user_without_lists(self):
        self.client.force_login(self.other)
        url = reverse("dashboard:detail", args=[self.share.pk])
        self.assertContains(self.client.get(url), "Создать список наблюдения")

    def test_share_page_for_anonymous_user_has_no_form(self):
        self.client.logout()
        url = reverse("dashboard:detail", args=[self.share.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "список наблюдения")

    def test_navigation_is_shown_only_after_login(self):
        link = self.url("list")
        self.assertContains(self.client.get(reverse("dashboard:index")), link)
        self.client.logout()
        self.assertNotContains(self.client.get(reverse("dashboard:index")), link)

    def test_share_with_monitoring_data_can_be_deleted(self):
        self.make_target()
        self.set_price(101.0)
        check_price_targets()
        response = self.client.post(reverse("dashboard:delete", args=[self.share.pk]))
        self.assertRedirects(response, reverse("dashboard:index"))
        self.assertFalse(Notification.objects.exists())
