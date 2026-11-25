"""Ingestion-backlog alert: ADMINS hear about it when fetched messages stop being
processed. Polls can keep succeeding (the polling freshness alert stays quiet)
while the capagg-ingestion worker is dead, and sweep_unprocessed re-enqueueing
does nothing if no one consumes the queue. Two signals:

- work waiting in the capagg-ingestion queue while the pipeline has written
  nothing for STALL_AFTER (a dead worker never creates a RawMessage, so this is
  the only trace it leaves);
- work that started and stuck: RawMessages in `received`/`validated`, or stored
  alerts never lineage-resolved, beyond STALL_AFTER.

Same debounce as the polling alert: once, a 24h reminder, once on recovery."""

from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from capaggregator.ingestion.alerting import BACKLOG_CACHE_KEY, STALL_AFTER, check_ingestion_backlog

from .factories import create_cap_alert, create_raw_message, create_source_authority

MIN = timedelta(minutes=1)


@override_settings(
    ADMINS=[("Ops", "ops@example.org")],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class IngestionBacklogAlertTests(TestCase):
    def setUp(self):
        cache.delete(BACKLOG_CACHE_KEY)
        self.authority = create_source_authority(name="Kenya Met")
        self.now = timezone.now()
        # Never read the real broker: the dev queue may hold anything
        self.queued = 0
        patcher = patch("capaggregator.ingestion.alerting._ingestion_queue_depth", side_effect=lambda: self.queued)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        cache.delete(BACKLOG_CACHE_KEY)

    def stuck(self, state="received", age=STALL_AFTER + MIN):
        return create_raw_message(self.authority, state=state, received_at=self.now - age)

    def test_no_backlog_sends_nothing(self):
        create_raw_message(self.authority, state="stored", received_at=self.now - 60 * MIN)

        self.assertIsNone(check_ingestion_backlog(now=self.now))
        self.assertEqual(len(mail.outbox), 0)

    def test_recently_received_messages_are_not_a_stall(self):
        self.stuck(age=STALL_AFTER - MIN)

        self.assertIsNone(check_ingestion_backlog(now=self.now))
        self.assertEqual(len(mail.outbox), 0)

    def test_messages_stuck_past_the_threshold_alert_admins_once(self):
        self.stuck("received")
        self.stuck("validated")

        self.assertEqual(check_ingestion_backlog(now=self.now), "stale")
        self.assertIsNone(check_ingestion_backlog(now=self.now + 5 * MIN))

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["ops@example.org"])
        self.assertIn("2 messages", message.subject)
        self.assertIn("capagg-worker-ingestion", message.body)

    def test_stored_but_unresolved_alerts_count_as_a_stall(self):
        alert = create_cap_alert(self.authority)  # chain=None: never lineage-resolved
        type(alert).objects.filter(pk=alert.pk).update(created=self.now - STALL_AFTER - MIN)

        self.assertEqual(check_ingestion_backlog(now=self.now), "stale")
        self.assertIn("1 stored alert", mail.outbox[0].body)

    def test_queued_work_with_no_pipeline_progress_alerts(self):
        """A dead ingestion worker creates no RawMessage rows; only the queue shows it."""
        create_raw_message(self.authority, state="stored", received_at=self.now - STALL_AFTER - MIN)
        self.queued = 42

        self.assertEqual(check_ingestion_backlog(now=self.now), "stale")
        self.assertIn("42 queued tasks", mail.outbox[0].subject)
        self.assertIn("nothing is consuming", mail.outbox[0].body)

    def test_queued_work_while_the_pipeline_progresses_is_not_a_stall(self):
        """A backfill legitimately queues thousands of messages."""
        create_raw_message(self.authority, state="stored", received_at=self.now - 2 * MIN)
        self.queued = 5000

        self.assertIsNone(check_ingestion_backlog(now=self.now))

    def test_duplicate_deliveries_count_as_progress(self):
        """Steady-state polling mostly re-delivers known bytes: receipts, no new rows."""
        from capaggregator.ingestion.models import DeliveryReceipt

        raw = create_raw_message(self.authority, state="stored", received_at=self.now - 60 * MIN)
        DeliveryReceipt.objects.create(authority=self.authority, transport="poll", raw_message=raw, was_first=False)
        self.queued = 3

        self.assertIsNone(check_ingestion_backlog(now=timezone.now()))

    def test_an_empty_queue_on_a_quiet_system_is_not_a_stall(self):
        create_raw_message(self.authority, state="stored", received_at=self.now - 600 * MIN)

        self.assertIsNone(check_ingestion_backlog(now=self.now))

    def test_unreadable_queue_depth_is_ignored(self):
        create_raw_message(self.authority, state="stored", received_at=self.now - 600 * MIN)
        self.queued = None  # broker unreachable

        self.assertIsNone(check_ingestion_backlog(now=self.now))

    def test_reminds_every_24h_while_the_backlog_persists(self):
        self.stuck()
        check_ingestion_backlog(now=self.now)

        self.assertIsNone(check_ingestion_backlog(now=self.now + 23 * 60 * MIN))
        self.assertEqual(check_ingestion_backlog(now=self.now + 24 * 60 * MIN), "reminder")
        self.assertIn("Still", mail.outbox[1].subject)

    def test_recovery_is_announced_once(self):
        raw = self.stuck()
        check_ingestion_backlog(now=self.now)

        raw.state = "stored"
        raw.save()

        self.assertEqual(check_ingestion_backlog(now=self.now + 5 * MIN), "recovered")
        self.assertIsNone(check_ingestion_backlog(now=self.now + 10 * MIN))
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("Recovered", mail.outbox[1].subject)

    def test_state_is_independent_of_the_polling_alert(self):
        """A polling outage being notified must not swallow the ingestion alert."""
        from capaggregator.ingestion.alerting import STATE_CACHE_KEY

        cache.set(STATE_CACHE_KEY, {"state": "stale", "notified_at": self.now}, timeout=None)
        try:
            self.stuck()
            self.assertEqual(check_ingestion_backlog(now=self.now), "stale")
        finally:
            cache.delete(STATE_CACHE_KEY)


class QueueDepthTests(TestCase):
    def depth_when_declare(self, **behaviour):
        from unittest.mock import MagicMock

        from capaggregator.ingestion.alerting import _ingestion_queue_depth

        conn = MagicMock()
        conn.__enter__.return_value.default_channel.queue_declare.configure_mock(**behaviour)
        with patch("capaggregator.config.celery.app.connection_for_read", return_value=conn):
            return _ingestion_queue_depth()

    def test_reads_the_message_count(self):
        from unittest.mock import MagicMock

        self.assertEqual(self.depth_when_declare(return_value=MagicMock(message_count=7)), 7)

    def test_an_emptied_redis_queue_reads_as_zero(self):
        from amqp.exceptions import ChannelError

        # Exactly what kombu's virtual transport raises (not amqp's NotFound subclass)
        empty = ChannelError("NOT_FOUND - no queue 'capagg-ingestion' in vhost '0'",
                             (50, 10), "Channel.queue_declare", "404")
        self.assertEqual(self.depth_when_declare(side_effect=empty), 0)

    def test_an_unreachable_broker_reads_as_unknown(self):
        self.assertIsNone(self.depth_when_declare(side_effect=ConnectionError("broker down")))


class BacklogCheckSchedulingTests(TestCase):
    def test_backlog_check_is_on_the_beat_schedule(self):
        from django.conf import settings

        by_task = {entry["task"]: entry["schedule"] for entry in settings.CELERY_BEAT_SCHEDULE.values()}

        self.assertEqual(by_task.get("capaggregator.ingestion.tasks.check_ingestion_backlog"), 300)
