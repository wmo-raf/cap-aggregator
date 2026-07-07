"""Phase B/4: re-running validation over quarantined messages — after an
authority's registration is corrected, a previously-rejected alert now passes and
is stored, and leaves the quarantine inbox."""

from unittest.mock import patch

from django.test import TestCase

from task_ferry.handler import JobHandler

from capaggregator.alerts.models import Alert
from capaggregator.ingestion.models import QuarantinedMessage, RawMessage
from capaggregator.ingestion.tasks import ingest_raw_message
from capaggregator.tests.cap_samples import cap_alert_xml
from capaggregator.tests.factories import create_source_authority


@patch("capaggregator.alerts.tasks.resolve_lineage")
class QuarantineRevalidationTests(TestCase):
    def test_correcting_the_authority_then_revalidating_stores_the_message(self, _resolve_lineage):
        authority = create_source_authority(name="Kenya Met", sender_values=["registered@met.ke"])
        # Arrives with a sender the authority does not (yet) accept → quarantined.
        result = ingest_raw_message(
            transport="manual", xml=cap_alert_xml(sender="new-office@met.ke"), authority_id=authority.id
        )
        self.assertEqual(result["state"], "quarantined")
        self.assertEqual(QuarantinedMessage.objects.filter(status="pending").count(), 1)

        # Operator corrects the registration, then re-runs validation.
        authority.sender_values = ["registered@met.ke", "new-office@met.ke"]
        authority.save(update_fields=["sender_values"])

        job = JobHandler.create_and_start(None, "quarantine_revalidation")
        JobHandler.run_by_id(job.id)

        self.assertEqual(RawMessage.objects.get(id=result["raw_id"]).state, "stored")
        self.assertEqual(QuarantinedMessage.objects.count(), 0)
        self.assertTrue(Alert.objects.filter(authority=authority, identifier="TEST-0001").exists())
