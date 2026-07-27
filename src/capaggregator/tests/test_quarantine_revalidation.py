"""Re-running validation over withheld messages.

Two outcomes matter now. A message that was withheld over a configuration
problem is released once the configuration is corrected — and a message that was
withheld under the old publish-nothing-defective policy leaves the register as a
published alert carrying its defects, which is how the existing backlog drains
after deploy.
"""

from unittest.mock import patch

from django.test import TestCase

from task_ferry.handler import JobHandler

from capaggregator.alerts.models import Alert
from capaggregator.ingestion import categories
from capaggregator.ingestion.models import QuarantinedMessage, RawMessage
from capaggregator.ingestion.tasks import ingest_raw_message
from capaggregator.tests.cap_samples import NOT_WELL_FORMED_XML, cap_alert_xml
from capaggregator.tests.factories import create_source_authority


def _revalidate():
    job = JobHandler.create_and_start(None, "quarantine_revalidation")
    JobHandler.run_by_id(job.id)
    return type(job).objects.get(pk=job.pk)


@patch("capaggregator.alerts.tasks.resolve_lineage")
class QuarantineRevalidationTests(TestCase):
    def test_correcting_the_signature_policy_then_revalidating_stores_the_message(self, _resolve):
        authority = create_source_authority(name="Kenya Met", signature_policy="require")
        # Unsigned under a policy that requires a signature → withheld.
        result = ingest_raw_message(transport="manual", xml=cap_alert_xml(), authority_id=authority.id)
        self.assertEqual(result["state"], "quarantined")
        self.assertEqual(QuarantinedMessage.objects.filter(status="pending").count(), 1)

        # Operator corrects the registration, then re-runs validation.
        authority.signature_policy = "verify_if_present"
        authority.save(update_fields=["signature_policy"])

        job = _revalidate()

        self.assertEqual(job.messages_stored, 1)
        self.assertEqual(RawMessage.objects.get(id=result["raw_id"]).state, "stored")
        self.assertEqual(QuarantinedMessage.objects.count(), 0)
        self.assertTrue(Alert.objects.filter(authority=authority, identifier="TEST-0001").exists())

    def test_a_message_withheld_over_a_defect_leaves_the_register_as_a_published_alert(self, _resolve):
        # The backlog case: withheld under the old policy over a schema fault we
        # now publish through. One sweep after deploy releases it, with the
        # findings kept as defects rather than thrown away.
        authority = create_source_authority(name="Benin Met")
        raw = RawMessage.objects.create(
            authority=authority, transport="poll", state="quarantined",
            xml=cap_alert_xml(altitude="Zou"), sha256="a" * 64,
        )
        QuarantinedMessage.objects.create(
            raw_message=raw, report={"errors": [{"check": "xsd", "message": "altitude is not a decimal"}],
                                     "warnings": []},
        )

        job = _revalidate()

        self.assertEqual(job.messages_stored, 1)
        self.assertEqual(QuarantinedMessage.objects.count(), 0, "it leaves the withheld register")
        alert = Alert.objects.get(raw_message=raw)
        self.assertEqual({d.category for d in alert.defects.all()}, {categories.SCHEMA})

    def test_a_message_that_still_cannot_be_published_stays_withheld(self, _resolve):
        authority = create_source_authority(name="Algeria Met")
        ingest_raw_message(transport="manual", xml=NOT_WELL_FORMED_XML, authority_id=authority.id)

        job = _revalidate()

        self.assertEqual(job.messages_still_quarantined, 1)
        self.assertEqual(QuarantinedMessage.objects.get().primary_category, categories.SCHEMA)
