"""The defect register: one immutable row per validation finding, on the alert.

Driven through the single ingestion entry point against real PostGIS, because
what an operator ends up counting is a property of the whole pipeline — which
check fires, whether the message is published at all, and what gets denormalized
onto the alert — not of the recording helper in isolation.
"""

from unittest.mock import patch

from django.test import TestCase

from task_ferry.handler import JobHandler

from capaggregator.alerts.models import Alert, AlertDefect
from capaggregator.ingestion import categories
from capaggregator.ingestion.tasks import ingest_raw_message
from capaggregator.tests.cap_samples import cap_alert_xml
from capaggregator.tests.factories import create_quarantined_message, create_source_authority

# 4 pairs, first != last: schema-valid and publishable, but the ring is not
# closed — the one warning-level finding a real message reaches us with.
UNCLOSED_RING = "-1.30,36.80 -1.30,36.90 -1.20,36.90 -1.20,36.80"


@patch("capaggregator.alerts.tasks.resolve_lineage")
class DefectRegisterTests(TestCase):
    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")

    def _store(self, xml=None):
        """Ingest `xml`, assert it published, and return the stored alert."""
        result = ingest_raw_message(
            transport="manual", xml=xml or cap_alert_xml(), authority_id=self.authority.id,
        )
        self.assertEqual(result["state"], "stored")
        return Alert.objects.get(id=result["alert_id"])

    def test_a_warning_level_finding_is_recorded_as_a_defect_row(self, _resolve):
        alert = self._store(cap_alert_xml(polygon=UNCLOSED_RING))

        defect = alert.defects.get()
        self.assertEqual(defect.check_name, "polygon-sanity")
        self.assertEqual(defect.category, categories.CONTENT)
        self.assertEqual(defect.severity, AlertDefect.WARNING)
        self.assertIn("ring not closed", defect.message)
        self.assertIsNotNone(defect.created)

    def test_the_defect_count_matches_the_rows(self, _resolve):
        # Two independent warnings: an unclosed ring and an info without <expires>.
        alert = self._store(cap_alert_xml(polygon=UNCLOSED_RING, expires=None))

        self.assertEqual(alert.defects.count(), 2)
        self.assertEqual(alert.defect_count, 2)
        self.assertEqual(Alert.objects.get(pk=alert.pk).defect_count, 2)

    def test_a_conformant_alert_carries_no_defects(self, _resolve):
        alert = self._store()

        self.assertEqual(alert.defects.count(), 0)
        self.assertEqual(alert.defect_count, 0)

    def test_a_defect_belongs_to_the_publishing_authority_through_its_alert(self, _resolve):
        self._store(cap_alert_xml(polygon=UNCLOSED_RING))

        self.assertEqual(
            AlertDefect.objects.filter(alert__authority=self.authority).count(), 1,
        )

    def test_a_defect_row_cannot_be_rewritten(self, _resolve):
        alert = self._store(cap_alert_xml(polygon=UNCLOSED_RING))
        defect = alert.defects.get()

        defect.message = "rewritten"
        with self.assertRaises(ValueError):
            defect.save()

        self.assertIn("ring not closed", AlertDefect.objects.get(pk=defect.pk).message)

    def test_a_defect_carries_no_status_field(self, _resolve):
        # The follow-up conversation happens per authority and per category, not
        # per finding — a per-row state would mean marking hundreds of rows to
        # record one email.
        self.assertNotIn("status", [f.name for f in AlertDefect._meta.get_fields()])

    def test_defects_survive_a_revalidation_sweep_of_unrelated_messages(self, _resolve):
        alert = self._store(cap_alert_xml(polygon=UNCLOSED_RING))
        create_quarantined_message(authority=self.authority)

        job = JobHandler.create_and_start(None, "quarantine_revalidation")
        JobHandler.run_by_id(job.id)

        alert.refresh_from_db()
        self.assertEqual(alert.defects.count(), 1)
        self.assertEqual(alert.defect_count, 1)
