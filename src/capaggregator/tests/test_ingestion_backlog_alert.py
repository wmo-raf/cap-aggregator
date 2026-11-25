"""Ingestion-backlog alert: ADMINS hear about it when fetched messages stop being
processed — RawMessages stuck in `received`/`validated`, or stored alerts never
lineage-resolved, beyond STALL_AFTER. Polls can keep succeeding (the polling
freshness alert stays quiet) while the capagg-ingestion worker is dead, and
sweep_unprocessed re-enqueueing does nothing if no one consumes the queue.

Same debounce as the polling alert: once, a 24h reminder, once on recovery."""

from datetime import timedelta

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


class BacklogCheckSchedulingTests(TestCase):
    def test_backlog_check_is_on_the_beat_schedule(self):
        from django.conf import settings

        by_task = {entry["task"]: entry["schedule"] for entry in settings.CELERY_BEAT_SCHEDULE.values()}

        self.assertEqual(by_task.get("capaggregator.ingestion.tasks.check_ingestion_backlog"), 300)
