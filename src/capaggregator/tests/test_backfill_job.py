"""Phase B/3: the manual backfill job runs an uploaded CAP .xml/.zip through the
standard ingestion pipeline, so dedup/validation/quarantine/lineage all apply, and
records found/stored/duplicate/quarantined counts."""

import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase

from task_ferry.handler import JobHandler

from capaggregator.ingestion.models import CapBackfillJob, QuarantinedMessage
from capaggregator.tests.cap_samples import cap_alert_xml
from capaggregator.tests.factories import create_source_authority


@patch("capaggregator.alerts.tasks.resolve_lineage")
class BackfillJobTests(TestCase):
    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")
        self.tmp = Path(tempfile.mkdtemp())

    def _run_backfill(self, file_path: Path) -> CapBackfillJob:
        job = JobHandler.create_and_start(
            None, "cap_backfill", authority_id=self.authority.id, file_path=str(file_path)
        )
        JobHandler.run_by_id(job.id)
        job.refresh_from_db()
        return job

    def test_single_valid_xml_is_stored(self, _resolve_lineage):
        xml_path = self.tmp / "alert.xml"
        xml_path.write_text(cap_alert_xml())

        job = self._run_backfill(xml_path)

        self.assertEqual(job.alerts_found, 1)
        self.assertEqual(job.alerts_stored, 1)

    def test_zip_with_valid_and_bad_docs_stores_one_and_quarantines_the_other(self, _resolve_lineage):
        zip_path = self.tmp / "batch.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("good.xml", cap_alert_xml(identifier="GOOD-1"))
            archive.writestr("bad.xml", cap_alert_xml(identifier="BAD-1", sender="unregistered@evil.test"))

        job = self._run_backfill(zip_path)

        self.assertEqual(job.alerts_found, 2)
        self.assertEqual(job.alerts_stored, 1)
        self.assertEqual(job.alerts_quarantined, 1)
        self.assertEqual(QuarantinedMessage.objects.count(), 1)
