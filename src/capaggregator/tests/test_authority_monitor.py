"""Health dashboard 3/5: the per-authority monitoring page — the drill-down from
the homepage panel's Detail button. Header facts, filterable tables, quarantine
strip. Smoke-level for the Wagtail plumbing; distinctive values asserted."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from capaggregator.ingestion.models import SourceEvent
from capaggregator.tests.factories import (
    create_quarantined_message,
    create_raw_message,
    create_source_authority,
)


class AuthorityMonitorTests(TestCase):
    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")
        self.user = get_user_model().objects.create_superuser("op", "op@example.test", "pw")
        self.client.force_login(self.user)

    def _url(self):
        return reverse("capagg_ingestion_authority_monitor", args=[self.authority.id])

    def test_page_loads_for_staff_with_header_facts(self):
        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kenya Met")
        self.assertContains(response, self.authority.feed_url)

    def test_header_shows_last_poll_error_when_the_last_poll_failed(self):
        SourceEvent.objects.create(authority=self.authority, transport="poll", ok=False, error="DISTINCT-POLL-ERROR")

        response = self.client.get(self._url())

        self.assertContains(response, "DISTINCT-POLL-ERROR")

    def test_state_filter_narrows_recent_messages(self):
        stored = create_raw_message(self.authority, state="stored")
        quarantined = create_raw_message(self.authority, state="quarantined")

        response = self.client.get(self._url(), {"state": "quarantined"})

        recent_ids = [m.id for m in response.context["recent_messages"]]
        self.assertIn(quarantined.id, recent_ids)
        self.assertNotIn(stored.id, recent_ids)

    def test_quarantine_strip_shows_pending_count(self):
        create_quarantined_message(authority=self.authority, status="pending")
        create_quarantined_message(authority=self.authority, status="dismissed")

        response = self.client.get(self._url())

        self.assertEqual(response.context["quarantine_pending_count"], 1)

    def test_monitor_requires_login(self):
        self.client.logout()

        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 302)

    def test_matrix_detail_url_resolves_to_this_page(self):
        from capaggregator.ingestion.health import build_health_matrix

        detail_url = build_health_matrix(days=1)["authorities"][0]["detail_url"]

        self.assertEqual(self.client.get(detail_url).status_code, 200)
