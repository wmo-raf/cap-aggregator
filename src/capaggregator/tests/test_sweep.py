"""The recovery sweep is the backstop for killed workers and exhausted retries:
messages stuck in 'received' re-enter the pipeline within ~10 minutes (5-min
cutoff on a 5-min schedule), and stored alerts that never got lineage-resolved
(crash between store and resolve) are re-enqueued for resolution instead of
staying invisible in resolved state forever."""

import hashlib
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from capaggregator.alerts.models import Alert
from capaggregator.ingestion.models import RawMessage
from capaggregator.ingestion.tasks import ingest_raw_message, sweep_unprocessed
from capaggregator.tests.cap_samples import cap_alert_xml
from capaggregator.tests.factories import create_source_authority


def stuck_raw_message(authority, xml, minutes_old, state="received"):
    raw = RawMessage.objects.create(
        transport="manual", xml=xml, sha256=hashlib.sha256(xml.encode()).hexdigest(),
        authority=authority, state=state,
    )
    RawMessage.objects.filter(id=raw.id).update(received_at=timezone.now() - timedelta(minutes=minutes_old))
    return raw


class SweepStuckMessagesTests(TestCase):
    @patch("capaggregator.ingestion.tasks.ingest_raw_message")
    def test_messages_stuck_beyond_five_minutes_reenter_the_pipeline(self, ingest):
        authority = create_source_authority()
        stuck = stuck_raw_message(authority, cap_alert_xml(), minutes_old=6)
        stuck_raw_message(authority, cap_alert_xml(identifier="urn:fresh"), minutes_old=2)

        sweep_unprocessed()

        self.assertEqual(ingest.delay.call_count, 1)
        self.assertEqual(ingest.delay.call_args.kwargs["xml"], stuck.xml)

    @patch("capaggregator.ingestion.tasks.ingest_raw_message")
    def test_messages_stuck_in_validated_are_also_rescued(self, ingest):
        # A crash (or a since-fixed deterministic failure, e.g. an oversized
        # column) between validate and store leaves state='validated'. If the
        # feed no longer lists the entry, nothing re-delivers it — only the
        # sweep can finish the job (re-execution resumes mid-flight messages).
        authority = create_source_authority()
        stuck = stuck_raw_message(authority, cap_alert_xml(), minutes_old=6, state="validated")

        sweep_unprocessed()

        self.assertEqual(ingest.delay.call_count, 1)
        self.assertEqual(ingest.delay.call_args.kwargs["xml"], stuck.xml)


class SweepUnresolvedAlertsTests(TestCase):
    def setUp(self):
        self.authority = create_source_authority()

    def stored_alert(self, minutes_old, identifier="urn:test:1"):
        with patch("capaggregator.alerts.tasks.resolve_lineage.delay"):
            result = ingest_raw_message(
                transport="manual", xml=cap_alert_xml(identifier=identifier), authority_id=self.authority.id
            )
        alert = Alert.objects.get(id=result["alert_id"])
        Alert.objects.filter(id=alert.id).update(created=timezone.now() - timedelta(minutes=minutes_old))
        return alert

    @patch("capaggregator.ingestion.tasks.ingest_raw_message")
    @patch("capaggregator.alerts.tasks.resolve_lineage")
    def test_stored_alerts_without_a_chain_are_reenqueued_for_resolution(self, resolve, ingest):
        orphaned = self.stored_alert(minutes_old=6, identifier="urn:orphaned")
        self.stored_alert(minutes_old=2, identifier="urn:fresh")

        sweep_unprocessed()

        resolved_ids = {call.args[0] for call in resolve.delay.call_args_list}
        self.assertEqual(resolved_ids, {orphaned.id})

    @patch("capaggregator.ingestion.tasks.ingest_raw_message")
    @patch("capaggregator.alerts.tasks.resolve_lineage")
    def test_alerts_already_attached_to_a_chain_are_left_alone(self, resolve, ingest):
        from capaggregator.alerts.lineage import resolve as real_resolve

        attached = self.stored_alert(minutes_old=6, identifier="urn:attached")
        real_resolve(attached)

        sweep_unprocessed()

        resolve.delay.assert_not_called()
