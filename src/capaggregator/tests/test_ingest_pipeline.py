"""Phase B/1: end-to-end smoke test proving a valid CAP message driven through the
single ingestion entry point reaches the stored state and produces an Alert.
This exercises validation, dedup, parse, and store together against real PostGIS."""

from unittest.mock import patch

from django.test import TestCase

from capaggregator.alerts.models import Alert
from capaggregator.ingestion.models import RawMessage
from capaggregator.ingestion.tasks import ingest_raw_message
from capaggregator.tests.cap_samples import cap_alert_xml
from capaggregator.tests.factories import create_source_authority


class IngestPipelineTests(TestCase):
    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")

    @patch("capaggregator.alerts.tasks.resolve_lineage")
    def test_valid_cap_message_is_stored(self, _resolve_lineage):
        result = ingest_raw_message(transport="manual", xml=cap_alert_xml(), authority_id=self.authority.id)

        self.assertEqual(result["state"], "stored")
        raw = RawMessage.objects.get(id=result["raw_id"])
        self.assertEqual(raw.state, "stored")
        self.assertTrue(Alert.objects.filter(id=result["alert_id"]).exists())
