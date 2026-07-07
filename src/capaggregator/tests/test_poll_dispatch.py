"""Phase B/1: the feed-poll dispatcher (poll_all_feeds) must poll each authority
at its adaptive cadence — the slow reconcile interval while a push transport is
healthy, the fast interval otherwise — dispatching a poll only for those due."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from capaggregator.ingestion import tasks
from capaggregator.ingestion.models import DeliveryReceipt

from .factories import create_source_authority


class PollDispatchTests(TestCase):
    @patch("capaggregator.ingestion.tasks.poll_feed")
    def test_reconcile_cadence_suppresses_healthy_push_source_while_feed_only_source_is_due(self, poll_feed):
        ten_minutes_ago = timezone.now() - timedelta(minutes=10)

        # Push transport healthy (recent MQTT receipt) → 30-min reconcile interval →
        # a 10-min-old poll is NOT yet due.
        push_source = create_source_authority(name="Push Source", mqtt_username="ke-push-source")
        push_source.feed_last_polled = ten_minutes_ago
        push_source.save(update_fields=["feed_last_polled"])
        DeliveryReceipt.objects.create(authority=push_source, transport="mqtt", was_first=True)

        # No push transport → 5-min fast interval → a 10-min-old poll IS due.
        feed_only_source = create_source_authority(name="Feed Only Source")
        feed_only_source.feed_last_polled = ten_minutes_ago
        feed_only_source.save(update_fields=["feed_last_polled"])

        tasks.poll_all_feeds()

        dispatched = {call.args[0] for call in poll_feed.delay.call_args_list}
        self.assertIn(feed_only_source.id, dispatched)
        self.assertNotIn(push_source.id, dispatched)
