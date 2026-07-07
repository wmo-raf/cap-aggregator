"""Phase B/5: the ingestion monitor lets an operator confirm alerts are landing —
a read-only admin list of raw messages with state, transport, and the
sent-vs-received latency, filterable by authority."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from capaggregator.ingestion.models import RawMessage
from capaggregator.ingestion.tasks import ingest_raw_message
from capaggregator.tests.cap_samples import cap_alert_xml
from capaggregator.tests.factories import create_source_authority


@patch("capaggregator.alerts.tasks.resolve_lineage")
class IngestLatencyTests(TestCase):
    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")

    def test_stored_message_latency_is_received_minus_sent(self, _resolve_lineage):
        result = ingest_raw_message(transport="manual", xml=cap_alert_xml(), authority_id=self.authority.id)

        raw = RawMessage.objects.get(id=result["raw_id"])
        self.assertEqual(raw.ingest_latency, raw.received_at - raw.sent_at)
        self.assertGreater(raw.ingest_latency, timedelta(0))

    def test_quarantined_message_without_sent_time_has_no_latency(self, _resolve_lineage):
        result = ingest_raw_message(
            transport="manual", xml=cap_alert_xml(sender="unregistered@x.test"), authority_id=self.authority.id
        )

        raw = RawMessage.objects.get(id=result["raw_id"])
        self.assertEqual(result["state"], "quarantined")
        self.assertIsNone(raw.ingest_latency)


class IngestionMonitorViewTests(TestCase):
    LIST_URL_NAME = "wagtailsnippets_capagg_ingestion_rawmessage:list"

    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")
        self.other = create_source_authority(name="Uganda Met", country="ug", sender_values=["u@x"])
        self.user = get_user_model().objects.create_superuser("op", "op@example.test", "pw")
        self.client.force_login(self.user)

    def _raw(self, authority, sha):
        return RawMessage.objects.create(
            authority=authority, transport="mqtt", xml="<alert/>", sha256=sha, state="stored"
        )

    def test_list_filters_by_authority(self):
        self._raw(self.authority, "a" * 64)
        self._raw(self.other, "b" * 64)

        response = self.client.get(reverse(self.LIST_URL_NAME), {"authority": self.authority.id})

        self.assertContains(response, "a" * 64)
        self.assertNotContains(response, "b" * 64)

    def test_monitor_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse(self.LIST_URL_NAME))

        self.assertEqual(response.status_code, 302)

    def test_raw_messages_cannot_be_edited(self):
        raw = self._raw(self.authority, "c" * 64)

        response = self.client.get(reverse("wagtailsnippets_capagg_ingestion_rawmessage:edit", args=[raw.pk]))

        self.assertNotEqual(response.status_code, 200)
