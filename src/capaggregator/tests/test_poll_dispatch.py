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

    @patch("capaggregator.ingestion.tasks.poll_feed")
    def test_due_check_tolerates_poll_duration_drift(self, poll_feed):
        # feed_last_polled is stamped at poll END, so requiring a full interval
        # would make every nonzero poll duration miss the next dispatcher tick
        # (1-min interval → effective 2 min). Half a tick of slack absorbs it.
        nearly_due = create_source_authority(name="Nearly Due")
        nearly_due.feed_last_polled = timezone.now() - timedelta(seconds=40)
        nearly_due.save(update_fields=["feed_last_polled"])

        fresh = create_source_authority(name="Fresh")
        fresh.feed_last_polled = timezone.now() - timedelta(seconds=20)
        fresh.save(update_fields=["feed_last_polled"])

        tasks.poll_all_feeds()

        dispatched = {call.args[0] for call in poll_feed.delay.call_args_list}
        self.assertIn(nearly_due.id, dispatched)
        self.assertNotIn(fresh.id, dispatched)

    def test_fast_poll_defaults_to_one_minute(self):
        # Alerts are time-sensitive: the poll-only worst case must be ~2 min
        # (interval + tick), so new authorities start at the 1-minute fast poll.
        authority = create_source_authority()
        self.assertEqual(authority.feed_poll_interval_minutes, 1)
