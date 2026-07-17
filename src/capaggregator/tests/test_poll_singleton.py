"""At most one in-flight poll per authority: the dispatcher re-scans every 60s
while feed_last_polled is stamped at poll END, so any poll slower than a tick
would otherwise get a second concurrent poll — racing conditional-GET state and
re-fetching the same entries."""

from unittest.mock import patch

from celery_singleton import clear_locks
from django.test import TestCase

from capaggregator.config.celery import app
from capaggregator.ingestion import tasks

from .factories import create_source_authority


class PollSingletonTests(TestCase):
    def setUp(self):
        clear_locks(app)

    def tearDown(self):
        clear_locks(app)

    @patch("celery.app.task.Task.apply_async")
    def test_second_enqueue_for_same_authority_is_suppressed(self, publish):
        authority = create_source_authority()

        tasks.poll_feed.delay(authority.id)
        tasks.poll_feed.delay(authority.id)

        self.assertEqual(publish.call_count, 1)

    @patch("celery.app.task.Task.apply_async")
    def test_different_authorities_are_not_deduplicated(self, publish):
        one = create_source_authority(name="One")
        two = create_source_authority(name="Two")

        tasks.poll_feed.delay(one.id)
        tasks.poll_feed.delay(two.id)

        self.assertEqual(publish.call_count, 2)

    @patch("capaggregator.sources.feeds.fetch_feed", return_value=([], False))
    @patch("celery.app.task.Task.apply_async")
    def test_completed_poll_releases_the_lock_for_the_next_cycle(self, publish, fetch_feed):
        authority = create_source_authority()

        tasks.poll_feed.delay(authority.id)
        tasks.poll_feed.apply(args=[authority.id])  # the in-flight poll finishes
        tasks.poll_feed.delay(authority.id)

        self.assertEqual(publish.call_count, 2)

    @patch("celery.app.task.Task.apply_async")
    def test_dispatcher_tick_overlapping_a_running_scan_is_a_noop(self, publish):
        tasks.poll_all_feeds.delay()
        tasks.poll_all_feeds.delay()

        self.assertEqual(publish.call_count, 1)

    @patch("celery.app.task.Task.apply_async")
    def test_failed_poll_releases_the_lock_for_the_next_cycle(self, publish):
        authority = create_source_authority()

        tasks.poll_feed.delay(authority.id)
        with patch("capaggregator.sources.models.SourceAuthority.objects.filter",
                   side_effect=RuntimeError("db blip")):
            result = tasks.poll_feed.apply(args=[authority.id])  # in-flight poll crashes
        self.assertTrue(result.failed())

        tasks.poll_feed.delay(authority.id)

        self.assertEqual(publish.call_count, 2)
