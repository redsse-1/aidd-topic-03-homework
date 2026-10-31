from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse, reverse_lazy

from dashboard.models import Share

User = get_user_model()
PASSWORD = "c0rrect-horse-battery"


class RegistrationTests(TestCase):
    url = reverse_lazy("user:registration")

    def register(self, email="ivan@mail.test", password1=PASSWORD, password2=PASSWORD):
        return self.client.post(
            self.url,
            {"email": email, "password1": password1, "password2": password2},
        )

    def test_registration_logs_user_in(self):
        response = self.register()
        self.assertRedirects(response, reverse("dashboard:index"))
        self.assertTrue(self.client.session.get("_auth_user_id"))

    def test_mixed_case_email_can_log_in(self):
        self.register(email="Ivan@Mail.test")
        self.client.logout()
        response = self.client.post(
            reverse("user:auth"), {"email": "Ivan@Mail.test", "password": PASSWORD}
        )
        self.assertRedirects(response, reverse("dashboard:index"))

    def test_email_is_unique_ignoring_case(self):
        self.register()
        self.client.logout()
        response = self.register(email="IVAN@mail.test")
        self.assertContains(response, "уже зарегистрирован")
        self.assertEqual(User.objects.count(), 1)

    def test_passwords_must_match(self):
        response = self.register(password2="another-Passw0rd")
        self.assertContains(response, "не совпадают")
        self.assertFalse(User.objects.exists())

    def test_weak_password_is_rejected(self):
        response = self.register(password1="1", password2="1")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_invalid_email_shows_error(self):
        response = self.register(email="not-an-email")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_empty_form_shows_error(self):
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 200)


class AuthTests(TestCase):
    def setUp(self):
        User.objects.create_user("ivan@mail.test", "ivan@mail.test", PASSWORD)

    def test_login_and_logout(self):
        response = self.client.post(
            reverse("user:auth"), {"email": "ivan@mail.test", "password": PASSWORD}
        )
        self.assertRedirects(response, reverse("dashboard:index"))
        response = self.client.get(reverse("dashboard:index"))
        self.assertContains(response, "ivan@mail.test")

        response = self.client.get(reverse("user:logout"))
        self.assertRedirects(response, reverse("dashboard:index"))
        self.assertFalse(self.client.session.get("_auth_user_id"))

    def test_wrong_password_shows_error(self):
        response = self.client.post(
            reverse("user:auth"), {"email": "ivan@mail.test", "password": "wrong"}
        )
        self.assertContains(response, "Неверный логин или пароль")

    def test_empty_form_shows_error(self):
        response = self.client.post(reverse("user:auth"), {})
        self.assertContains(response, "Неверный логин или пароль")


class ShareManagementAccessTests(TestCase):
    """Управление акциями в веб-интерфейсе"""

    data = {
        "figi": "F1",
        "isin": "I1",
        "name": "Company",
        "ticker": "TST",
        "currency": "rub",
        "uid": "U1",
    }

    def setUp(self):
        self.user = User.objects.create_user("ivan@mail.test", "ivan@mail.test", PASSWORD)

    def test_anonymous_user_is_redirected(self):
        response = self.client.post(reverse("dashboard:create"), self.data)
        self.assertRedirects(response, reverse("dashboard:index"))
        self.assertFalse(Share.objects.exists())

    def test_user_can_create_update_and_delete(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("dashboard:create"), self.data)
        self.assertRedirects(response, reverse("dashboard:index"))
        share = Share.objects.get()

        response = self.client.post(
            reverse("dashboard:update", args=[share.id]), {**self.data, "name": "New"}
        )
        self.assertRedirects(response, reverse("dashboard:index"))
        share.refresh_from_db()
        self.assertEqual(share.name, "New")

        response = self.client.get(reverse("dashboard:delete", args=[share.id]))
        self.assertContains(response, "New")
        response = self.client.post(reverse("dashboard:delete", args=[share.id]))
        self.assertRedirects(response, reverse("dashboard:index"))
        self.assertFalse(Share.objects.exists())

    def test_form_pages_render(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("dashboard:create")).status_code, 200)

    def test_duplicate_ticker_is_rejected(self):
        self.client.force_login(self.user)
        self.client.post(reverse("dashboard:create"), self.data)
        response = self.client.post(
            reverse("dashboard:create"), {**self.data, "figi": "F2", "uid": "U2"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Share.objects.count(), 1)
