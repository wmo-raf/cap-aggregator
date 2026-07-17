"""A transient error (DB hiccup, momentary blip) must cost seconds, not a
sweep cycle: pipeline tasks autoretry transient errors with backoff, and
re-execution of the same bytes RESUMES a mid-flight raw message instead of
short-circuiting into the duplicate path. Validation failures never retry."""

from unittest.mock import patch

from django.db import OperationalError
from django.test import TestCase

from capaggregator.alerts import parser
from capaggregator.alerts.models import Alert
from capaggregator.ingestion.models import DeliveryReceipt, RawMessage
from capaggregator.ingestion.tasks import ingest_raw_message
from capaggregator.tests.cap_samples import cap_alert_xml
from capaggregator.tests.factories import create_source_authority


class TransientBlip:
    """Raise OperationalError for the first N calls, then defer to the real callable."""

    def __init__(self, real, failures=1):
        self.real = real
        self.failures = failures
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise OperationalError("connection dropped")
        return self.real(*args, **kwargs)


class IngestAutoretryTests(TestCase):
    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")

    @patch("capaggregator.alerts.tasks.resolve_lineage")
    def test_transient_db_error_retries_to_a_stored_alert(self, _resolve_lineage):
        flaky_store = TransientBlip(parser.parse_and_store, failures=1)

        with patch("capaggregator.alerts.parser.parse_and_store", side_effect=flaky_store):
            result = ingest_raw_message.apply(
                kwargs=dict(transport="manual", xml=cap_alert_xml(), authority_id=self.authority.id)
            )

        self.assertTrue(result.successful())
        self.assertEqual(result.result["state"], "stored")
        self.assertEqual(flaky_store.calls, 2)
        self.assertEqual(Alert.objects.count(), 1)
        self.assertEqual(DeliveryReceipt.objects.filter(was_first=True).count(), 1)
        raw = RawMessage.objects.get()
        self.assertEqual(raw.state, "stored")

    def test_validation_failure_quarantines_once_without_retrying(self):
        result = ingest_raw_message.apply(
            kwargs=dict(transport="manual", xml=cap_alert_xml(sender="unregistered@x.test"),
                        authority_id=self.authority.id)
        )

        self.assertTrue(result.successful())
        self.assertEqual(result.result["state"], "quarantined")
        self.assertEqual(RawMessage.objects.get().state, "quarantined")

    @patch("capaggregator.alerts.tasks.resolve_lineage")
    def test_redelivery_of_completed_bytes_still_short_circuits_as_duplicate(self, _resolve_lineage):
        xml = cap_alert_xml()
        ingest_raw_message(transport="manual", xml=xml, authority_id=self.authority.id)

        result = ingest_raw_message(transport="manual", xml=xml, authority_id=self.authority.id)

        self.assertEqual(result["state"], "duplicate")
        self.assertEqual(Alert.objects.count(), 1)
        self.assertEqual(DeliveryReceipt.objects.filter(was_first=False).count(), 1)

    @patch("capaggregator.alerts.tasks.resolve_lineage")
    def test_reexecution_resumes_a_mid_flight_raw_message(self, _resolve_lineage):
        # A worker that died between store-attempt and completion leaves the raw
        # message in a non-terminal state; the sweep (and celery retries) re-run
        # the task with the same bytes — that must finish the job, not record a
        # bogus duplicate receipt.
        xml = cap_alert_xml()
        stuck = RawMessage.objects.create(
            transport="manual", xml=xml,
            sha256=__import__("hashlib").sha256(xml.encode()).hexdigest(),
            authority=self.authority, state="received",
        )

        result = ingest_raw_message(transport="manual", xml=xml, authority_id=self.authority.id)

        self.assertEqual(result["state"], "stored")
        stuck.refresh_from_db()
        self.assertEqual(stuck.state, "stored")
        self.assertEqual(Alert.objects.count(), 1)
        self.assertEqual(DeliveryReceipt.objects.filter(was_first=True).count(), 1)
        self.assertEqual(DeliveryReceipt.objects.filter(was_first=False).count(), 0)


class LineageAutoretryTests(TestCase):
    def test_transient_error_during_resolution_retries_to_success(self):
        from capaggregator.alerts import lineage, tasks as alert_tasks

        authority = create_source_authority(name="Kenya Met")
        with patch("capaggregator.alerts.tasks.resolve_lineage.delay"):
            stored = ingest_raw_message(transport="manual", xml=cap_alert_xml(), authority_id=authority.id)
        flaky_resolve = TransientBlip(lineage.resolve, failures=1)

        with patch("capaggregator.alerts.lineage.resolve", side_effect=flaky_resolve):
            result = alert_tasks.resolve_lineage.apply(args=[stored["alert_id"]])

        self.assertTrue(result.successful())
        self.assertEqual(flaky_resolve.calls, 2)
        alert = Alert.objects.get(id=stored["alert_id"])
        self.assertIsNotNone(alert.chain)
