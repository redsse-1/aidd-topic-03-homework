from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from dashboard.models import Share


class DashboardTests(APITestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user("api@test.local")
        self.client.force_authenticate(self.user)

        self.apple_share = Share.objects.create(
            figi="BBG000B9XRY4",
            isin="US0378331005",
            name="Apple",
            ticker="AAPL",
            currency="usd",
            uid="a9eb4238-eba9-488c-b102-b6140fd08e38",
            last_price=100.50,
            is_trend_high=True,
        )

        self.second_company = {
            "figi": "BBG000B9XRY5",
            "isin": "US0378331004",
            "name": "Company_test",
            "ticker": "TESTTEST",
            "currency": "usd",
            "uid": "a9eb4238-eba9-488c-b102-b6140fd08e39",
            "last_price": 1.50,
            "is_trend_high": False,
        }

    def test_share_list_html(self):
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_share_list(self):
        response = self.client.get("/api/v1/shares/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        apple_share = response.json().get("results")[0]
        self.assertEqual(apple_share["id"], self.apple_share.id)
        self.assertEqual(apple_share["figi"], self.apple_share.figi)
        self.assertEqual(apple_share["isin"], self.apple_share.isin)
        self.assertEqual(apple_share["name"], self.apple_share.name)
        self.assertEqual(apple_share["ticker"], self.apple_share.ticker)
        self.assertEqual(apple_share["currency"], self.apple_share.currency)

    def test_share_detail(self):
        response = self.client.get("/api/v1/shares/")
        share_detail = response.json().get("results")[0]
        response = self.client.get(f"/api/v1/shares/{share_detail['id']}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_share_detail_invalid(self):
        response = self.client.get(f"/api/v1/shares/{self.apple_share.id + 1}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_share_update(self):
        response = self.client.get("/api/v1/shares/")
        share_detail = response.json().get("results")[0]
        response = self.client.put(
            f"/api/v1/shares/{share_detail['id']}/",
            {
                "id": share_detail["id"],
                "figi": self.apple_share.figi,
                "isin": self.apple_share.isin,
                "name": f"{self.apple_share.name}_test",
                "ticker": self.apple_share.ticker,
                "currency": self.apple_share.currency,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(body["figi"], self.apple_share.figi)
        self.assertEqual(body["name"], f"{self.apple_share.name}_test")

    def test_share_update_invalid(self):
        response = self.client.get("/api/v1/shares/")
        share_detail = response.json().get("results")[0]
        response = self.client.put(
            f"/api/v1/shares/{share_detail['id']}/",
            {
                "figi": self.apple_share.figi,
                "name": f"{self.apple_share.name}_test",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_share_create(self):
        response = self.client.post(
            "/api/v1/shares/", self.second_company, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()
        self.assertEqual(body["figi"], self.second_company["figi"])
        self.assertEqual(body["name"], self.second_company["name"])
        self.assertEqual(body["ticker"], self.second_company["ticker"])

        response = self.client.get("/api/v1/shares/")
        self.assertEqual(len(response.data["results"]), 2)

    def test_share_create_invalid(self):
        response = self.client.post(
            "/api/v1/shares/", {"figi": "BBG000B9XRY5"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_share_delete(self):
        response = self.client.get("/api/v1/shares/")
        share_detail = response.json().get("results")[0]
        response = self.client.delete(f"/api/v1/shares/{share_detail['id']}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        response = self.client.get("/api/v1/shares/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 0)

    def test_second_share_can_be_created_without_uid(self):
        first = {**self.second_company}
        first.pop("uid")
        second = {**first, "figi": "F3", "isin": "I3", "ticker": "TEST3"}

        for data in (first, second):
            response = self.client.post("/api/v1/shares/", data, format="json")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_invalid_search_regex_gives_400(self):
        response = self.client.get("/api/v1/shares/", {"search": "("})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_search_filter_and_ordering(self):
        response = self.client.get("/api/v1/shares/", {"search": "^app"})
        self.assertEqual(len(response.data["results"]), 1)
        response = self.client.get("/api/v1/shares/", {"ticker": "AAPL"})
        self.assertEqual(len(response.data["results"]), 1)
        response = self.client.get("/api/v1/shares/", {"ticker": "NONE"})
        self.assertEqual(len(response.data["results"]), 0)
        response = self.client.get("/api/v1/shares/", {"ordering": "-ticker"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_anonymous_client_can_read_but_not_write(self):
        self.client.force_authenticate(None)
        url = f"/api/v1/shares/{self.apple_share.id}/"

        self.assertEqual(self.client.get("/api/v1/shares/").status_code, 200)
        self.assertEqual(self.client.get(url).status_code, 200)
        requests = (
            self.client.post("/api/v1/shares/", self.second_company, format="json"),
            self.client.patch(url, {"name": "x"}, format="json"),
            self.client.delete(url),
        )
        for response in requests:
            self.assertIn(
                response.status_code,
                (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
            )
        self.assertTrue(Share.objects.filter(id=self.apple_share.id).exists())

    def test_share_delete_invalid(self):
        response = self.client.delete(f"/api/v1/shares/{self.apple_share.id + 1}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
