from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from dashboard.models import (
    PriceNotification,
    Share,
    Watchlist,
    WatchlistEntry,
)
from dashboard.services.price_monitor import evaluate_price_alerts
from dashboard.services.market_data import Quote
from dashboard.tasks import update_last_price


class PersonalMonitoringTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            "watcher@example.com", "watcher@example.com", "long-test-password"
        )
        self.other_user = user_model.objects.create_user(
            "other-watcher@example.com",
            "other-watcher@example.com",
            "long-test-password",
        )
        self.share = Share.objects.create(
            figi="MOEX:TQBR:SBER",
            isin="RU0009029540",
            name="Сбербанк",
            ticker="SBER",
            currency="rub",
            uid="MOEX:TQBR:SBER",
            last_price=Decimal("101"),
        )
        self.watchlist = Watchlist.objects.create(
            owner=self.owner, name="Мои акции"
        )
        self.entry = WatchlistEntry.objects.create(
            watchlist=self.watchlist,
            share=self.share,
            direction=WatchlistEntry.Direction.AT_OR_ABOVE,
            target_price=Decimal("100"),
        )

    def test_alert_is_created_once_until_price_leaves_and_reenters_target(self):
        self.assertEqual(evaluate_price_alerts(self.share.pk, Decimal("101")), 1)
        self.assertEqual(evaluate_price_alerts(self.share.pk, Decimal("102")), 0)
        self.assertEqual(evaluate_price_alerts(self.share.pk, Decimal("100")), 0)
        self.assertEqual(PriceNotification.objects.count(), 1)

        self.assertEqual(evaluate_price_alerts(self.share.pk, Decimal("99")), 0)
        self.assertEqual(evaluate_price_alerts(self.share.pk, Decimal("100")), 1)
        self.assertEqual(PriceNotification.objects.count(), 2)

    def test_below_target_triggers_at_boundary_and_rearms_above_it(self):
        self.entry.direction = WatchlistEntry.Direction.AT_OR_BELOW
        self.entry.target_price = Decimal("95")
        self.entry.save()

        self.assertEqual(evaluate_price_alerts(self.share.pk, Decimal("95")), 1)
        self.assertEqual(evaluate_price_alerts(self.share.pk, Decimal("90")), 0)
        self.assertEqual(evaluate_price_alerts(self.share.pk, Decimal("96")), 0)
        self.assertEqual(evaluate_price_alerts(self.share.pk, Decimal("95")), 1)
        self.assertEqual(PriceNotification.objects.count(), 2)

    def test_existing_quote_update_task_evaluates_price_alerts_once(self):
        observed_at = datetime(2026, 10, 28, 10, 0, tzinfo=datetime_timezone.utc)
        with patch("dashboard.tasks.get_market_data_provider") as provider_factory:
            provider_factory.return_value.get_quotes.return_value = {
                self.share.figi: Quote(Decimal("101"), observed_at)
            }
            self.assertEqual(update_last_price(), 1)
        with patch("dashboard.tasks.get_market_data_provider") as provider_factory:
            provider_factory.return_value.get_quotes.return_value = {
                self.share.figi: Quote(Decimal("102"), observed_at)
            }
            self.assertEqual(update_last_price(), 1)
        self.assertEqual(PriceNotification.objects.count(), 1)

    def test_watchlists_entries_and_notifications_are_private(self):
        second_list = Watchlist.objects.create(
            owner=self.other_user, name="Чужой список"
        )
        PriceNotification.objects.create(
            entry=self.entry,
            triggered_price=Decimal("101"),
            triggered_at=datetime.now(datetime_timezone.utc),
            message="Событие для владельца",
        )
        self.client.force_login(self.other_user)

        response = self.client.get(reverse("dashboard:watchlist-list"))
        self.assertEqual(list(response.context["watchlists"]), [second_list])
        self.assertEqual(
            self.client.get(
                reverse("dashboard:watchlist-detail", args=[self.watchlist.pk])
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse(
                    "dashboard:watchlist-entry-delete", args=[self.entry.pk]
                )
            ).status_code,
            404,
        )
        notifications = self.client.get(reverse("dashboard:notifications"))
        self.assertEqual(len(notifications.context["notifications"]), 0)

        self.client.force_login(self.owner)
        notifications = self.client.get(reverse("dashboard:notifications"))
        self.assertEqual(len(notifications.context["notifications"]), 1)

    def test_owner_can_create_watchlist_and_target_entry(self):
        self.client.force_login(self.owner)
        create_response = self.client.post(
            reverse("dashboard:watchlist-list"), {"name": "Новый список"}
        )
        created_list = Watchlist.objects.get(name="Новый список")
        self.assertEqual(created_list.owner, self.owner)
        self.assertRedirects(
            create_response,
            reverse("dashboard:watchlist-detail", args=[created_list.pk]),
        )

        response = self.client.post(
            reverse("dashboard:watchlist-detail", args=[created_list.pk]),
            {
                "share": self.share.pk,
                "direction": WatchlistEntry.Direction.AT_OR_BELOW,
                "target_price": "90",
            },
        )
        self.assertEqual(response.status_code, 302)
        entry = WatchlistEntry.objects.get(watchlist=created_list)
        self.assertEqual(entry.share, self.share)
        self.assertEqual(entry.target_price, Decimal("90"))

    def test_invalid_watchlist_submission_keeps_form_errors(self):
        self.client.force_login(self.owner)

        response = self.client.post(reverse("dashboard:watchlist-list"), {"name": ""})

        self.assertEqual(response.status_code, 200)
        self.assertIn("name", response.context["form"].errors)

    def test_owner_cannot_add_same_share_twice_to_one_list(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("dashboard:watchlist-detail", args=[self.watchlist.pk]),
            {
                "share": self.share.pk,
                "direction": WatchlistEntry.Direction.AT_OR_BELOW,
                "target_price": "90",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Эта акция уже есть",
            str(response.context["entry_form"].errors),
        )
        self.assertEqual(self.watchlist.entries.count(), 1)

    def test_owner_can_update_target_and_other_user_cannot(self):
        self.client.force_login(self.other_user)
        denied = self.client.post(
            reverse("dashboard:watchlist-entry-update", args=[self.entry.pk]),
            {
                "direction": WatchlistEntry.Direction.AT_OR_BELOW,
                "target_price": "90",
            },
        )
        self.assertEqual(denied.status_code, 404)

        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("dashboard:watchlist-entry-update", args=[self.entry.pk]),
            {
                "direction": WatchlistEntry.Direction.AT_OR_BELOW,
                "target_price": "90",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.target_price, Decimal("90"))
        self.assertFalse(self.entry.is_triggered)

    def test_saving_unchanged_target_does_not_rearm_alert(self):
        self.entry.is_triggered = True
        self.entry.last_checked_price = Decimal("101")
        self.entry.save()
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("dashboard:watchlist-entry-update", args=[self.entry.pk]),
            {
                "direction": WatchlistEntry.Direction.AT_OR_ABOVE,
                "target_price": "100",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.entry.refresh_from_db()
        self.assertTrue(self.entry.is_triggered)
        self.assertEqual(self.entry.last_checked_price, Decimal("101"))

    def test_watchlist_can_only_be_deleted_by_owner(self):
        self.client.force_login(self.other_user)
        self.assertEqual(
            self.client.post(
                reverse("dashboard:watchlist-delete", args=[self.watchlist.pk])
            ).status_code,
            404,
        )
        self.assertTrue(Watchlist.objects.filter(pk=self.watchlist.pk).exists())

        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("dashboard:watchlist-delete", args=[self.watchlist.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Watchlist.objects.filter(pk=self.watchlist.pk).exists())

    def test_notification_read_action_is_owner_scoped(self):
        notification = PriceNotification.objects.create(
            entry=self.entry,
            triggered_price=Decimal("101"),
            triggered_at=datetime.now(datetime_timezone.utc),
            message="Событие для владельца",
        )
        self.client.force_login(self.other_user)

        self.assertEqual(
            self.client.post(
                reverse("dashboard:notification-read", args=[notification.pk])
            ).status_code,
            404,
        )
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

        self.client.force_login(self.owner)
        self.assertEqual(
            self.client.post(
                reverse("dashboard:notification-read", args=[notification.pk])
            ).status_code,
            302,
        )
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
