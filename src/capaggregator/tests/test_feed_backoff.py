"""Persistently failing feeds must back off instead of burning a full-timeout
connection every fast-poll cycle forever: consecutive failures double the
effective interval (1→2→4… min) capped at the reconcile interval, and a single
success snaps the authority back to full cadence."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from capaggregator.ingestion import tasks

from .factories import create_source_authority


def authority_polled_minutes_ago(minutes, **kwargs):
    authority = create_source_authority(**kwargs)
    authority.feed_last_polled = timezone.now() - timedelta(minutes=minutes)
    authority.save(update_fields=["feed_last_polled"])
    return authority


@patch("capaggregator.ingestion.tasks.poll_feed")
class BackoffDispatchTests(TestCase):
    def dispatched(self, poll_feed):
        tasks.poll_all_feeds()
        return {call.args[0] for call in poll_feed.delay.call_args_list}

    def test_consecutive_failures_double_the_effective_interval(self, poll_feed):
        # fast interval 1 min, 2 failures → effective 4 min: a 2-min-old poll
        # is not yet due, a 5-min-old one is
        backing_off = authority_polled_minutes_ago(2, name="Backing Off", feed_consecutive_failures=2)
        overdue = authority_polled_minutes_ago(5, name="Overdue", feed_consecutive_failures=2)

        dispatched = self.dispatched(poll_feed)

        self.assertNotIn(backing_off.id, dispatched)
        self.assertIn(overdue.id, dispatched)

    def test_backoff_is_capped_at_the_reconcile_interval(self, poll_feed):
        # 10 failures would mean 2^10 minutes uncapped; the cap is the 30-min
        # reconcile interval, so a 31-min-old poll is due again
        capped = authority_polled_minutes_ago(31, name="Capped", feed_consecutive_failures=10)
        waiting = authority_polled_minutes_ago(20, name="Waiting", feed_consecutive_failures=10)

        dispatched = self.dispatched(poll_feed)

        self.assertIn(capped.id, dispatched)
        self.assertNotIn(waiting.id, dispatched)

    def test_an_authority_without_failures_keeps_full_cadence(self, poll_feed):
        healthy = authority_polled_minutes_ago(2, name="Healthy")

        dispatched = self.dispatched(poll_feed)

        self.assertIn(healthy.id, dispatched)


class FailureCounterTests(TestCase):
    @patch("capaggregator.sources.feeds.fetch_feed", side_effect=ConnectionError("refused"))
    def test_each_failed_poll_increments_the_consecutive_failure_count(self, fetch_feed):
        authority = create_source_authority()

        tasks.poll_feed.apply(args=[authority.id])
        tasks.poll_feed.apply(args=[authority.id])

        authority.refresh_from_db()
        self.assertEqual(authority.feed_consecutive_failures, 2)

    @patch("capaggregator.sources.feeds.fetch_feed", return_value=([], False))
    def test_a_successful_poll_resets_the_consecutive_failure_count(self, fetch_feed):
        authority = create_source_authority(feed_consecutive_failures=3)

        tasks.poll_feed.apply(args=[authority.id])

        authority.refresh_from_db()
        self.assertEqual(authority.feed_consecutive_failures, 0)
