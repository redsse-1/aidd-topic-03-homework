from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from user.forms import RegistrationForm


class RegistrationTests(TestCase):
    def test_registration_creates_user_and_signs_them_in(self):
        response = self.client.post(
            reverse("user:registration"),
            {
                "email": "new@example.com",
                "password1": "long-test-password",
                "password2": "long-test-password",
            },
        )

        self.assertRedirects(response, reverse("dashboard:index"))
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_registration_rejects_duplicate_email_case_insensitively(self):
        get_user_model().objects.create_user(
            "existing@example.com", "existing@example.com", "long-test-password"
        )
        form = RegistrationForm(
            {
                "email": "Existing@example.com",
                "password1": "long-test-password",
                "password2": "long-test-password",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_registration_rejects_mismatched_passwords(self):
        form = RegistrationForm(
            {
                "email": "new@example.com",
                "password1": "first-password",
                "password2": "second-password",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)

    def test_login_with_missing_fields_returns_validation_errors(self):
        response = self.client.post(reverse("user:auth"), {"email": "bad"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.context)

    def test_authentication_urls_have_separating_slashes(self):
        self.assertEqual(reverse("user:auth"), "/user/login/")
        self.assertEqual(reverse("user:registration"), "/user/registration/")
        self.assertEqual(reverse("user:logout"), "/user/logout/")
