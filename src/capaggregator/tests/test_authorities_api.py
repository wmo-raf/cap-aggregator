"""Public read-only authorities API: feeds the explorer's Authorities view.
Exposes only public-safe fields — transport/credential data must never leak."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from capaggregator.tests.factories import create_event_chain, create_source_authority


class AuthoritiesApiTests(TestCase):
    def list_authorities(self):
        response = self.client.get(reverse("authority_list"))
        self.assertEqual(response.status_code, 200)
        return response.json()["results"]

    def test_lists_active_authorities_with_public_fields(self):
        create_source_authority(name="Kenya Met", country="ke", website="https://meteo.go.ke")

        results = self.list_authorities()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Kenya Met")
        self.assertEqual(results[0]["slug"], "kenya-met")
        self.assertEqual(results[0]["country"], "KE")
        self.assertEqual(results[0]["website"], "https://meteo.go.ke")

    def test_inactive_authorities_are_not_listed(self):
        create_source_authority(name="Active Met", country="ke")
        create_source_authority(name="Retired Met", country="ug", sender_values=["r@x"], active=False)

        results = self.list_authorities()

        self.assertEqual([a["name"] for a in results], ["Active Met"])

    def test_active_alert_count_excludes_cancelled_and_expired(self):
        authority = create_source_authority(name="Kenya Met")
        create_event_chain(authority)  # live
        create_event_chain(authority, is_cancelled=True)  # cancelled — not counted
        create_event_chain(authority, status="Test")  # drill — not a public warning
        past = timezone.now() - timedelta(days=3)
        create_event_chain(  # expired — not counted
            authority, sent=past, infos=[{"effective": past, "expires": past + timedelta(hours=1)}]
        )
        quiet = create_source_authority(name="Uganda Met", country="ug", sender_values=["u@x"])

        results = self.list_authorities()

        by_name = {a["name"]: a["active_alert_count"] for a in results}
        self.assertEqual(by_name["Kenya Met"], 1)
        self.assertEqual(by_name["Uganda Met"], 0)
        self.assertIsNotNone(quiet)

    def test_no_credential_or_transport_fields_are_ever_serialized(self):
        create_source_authority(name="Kenya Met")

        result = self.list_authorities()[0]

        forbidden = {
            "mqtt_username", "mqtt_password_hash", "mqtt_topic", "webhook_token",
            "certificate_pem", "sender_values", "contact_email", "feed_url",
            "signature_policy", "wmo_guid",
        }
        self.assertEqual(set(result) & forbidden, set())
        self.assertEqual(
            set(result),
            {"name", "slug", "country", "country_name", "website", "active_alert_count"},
        )

    def test_endpoint_is_documented_in_the_openapi_schema(self):
        response = self.client.get(reverse("api_schema"))

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/api/authorities/", response.content)
