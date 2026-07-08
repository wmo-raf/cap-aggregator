"""Health dashboard 2/5: the staff-gated JSON endpoint the panel and monitor page
consume. Behaviour of the matrix itself is covered in test_health_matrix."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from capaggregator.tests.factories import create_raw_message, create_source_authority


class HealthEndpointTests(TestCase):
    URL_NAME = "capagg_ingestion_health_api"

    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")
        self.user = get_user_model().objects.create_superuser("op", "op@example.test", "pw")
        self.client.force_login(self.user)

    def test_endpoint_returns_documented_shape_for_staff(self):
        response = self.client.get(reverse(self.URL_NAME))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["days"]), 30)
        self.assertIn("mqtt_consumer_connected", data)
        row = data["authorities"][0]
        self.assertEqual(row["name"], "Kenya Met")
        self.assertTrue(row["detail_url"].endswith("/monitor/"))

    def test_single_authority_mode_returns_per_day_counts(self):
        create_source_authority(name="Uganda Met", country="ug", sender_values=["u@x"])
        create_raw_message(self.authority, state="stored")  # today (auto received_at)

        response = self.client.get(reverse(self.URL_NAME), {"authority": self.authority.id})

        data = response.json()
        self.assertEqual(len(data["authorities"]), 1)
        self.assertEqual(data["authorities"][0]["id"], self.authority.id)
        self.assertEqual(data["authorities"][0]["counts"][-1]["stored"], 1)

    def test_days_param_is_honored_and_capped_at_90(self):
        self.assertEqual(len(self.client.get(reverse(self.URL_NAME), {"days": 7}).json()["days"]), 7)
        self.assertEqual(len(self.client.get(reverse(self.URL_NAME), {"days": 999}).json()["days"]), 90)

    def test_mqtt_consumer_connected_reflects_latest_connectivity_event(self):
        from capaggregator.tests.factories import create_source_event

        url = reverse(self.URL_NAME)
        self.assertTrue(self.client.get(url).json()["mqtt_consumer_connected"])

        create_source_event(authority=None, ok=False, transport="mqtt")  # disconnect
        self.assertFalse(self.client.get(url).json()["mqtt_consumer_connected"])

        create_source_event(authority=None, ok=True, transport="mqtt")  # reconnect
        self.assertTrue(self.client.get(url).json()["mqtt_consumer_connected"])

    def test_endpoint_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse(self.URL_NAME))

        self.assertEqual(response.status_code, 302)
