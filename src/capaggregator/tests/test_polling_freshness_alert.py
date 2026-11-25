"""Polling-freshness alert: ADMINS are emailed once when feed polling goes stale,
reminded every 24h while it stays stale, and told once when it recovers — so a
wedged polling worker can no longer go unnoticed for weeks (prod, Nov 2026)."""

from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from capaggregator.ingestion.alerting import STATE_CACHE_KEY, check_polling_freshness
from capaggregator.ingestion.models import SourceEvent

from .factories import create_source_authority

MIN = timedelta(minutes=1)


@override_settings(
    ADMINS=[("Ops", "ops@example.org")],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class PollingFreshnessAlertTests(TestCase):
    def setUp(self):
        cache.delete(STATE_CACHE_KEY)
        self.authority = create_source_authority(name="Kenya Met")
        self.t0 = timezone.now()

    def tearDown(self):
        cache.delete(STATE_CACHE_KEY)

    def poll(self, ok=True, error=""):
        return SourceEvent.objects.create(authority=self.authority, transport="poll", ok=ok, error=error)

    def test_fresh_polling_sends_nothing(self):
        self.poll()

        self.assertIsNone(check_polling_freshness(now=self.t0 + 5 * MIN))
        self.assertEqual(len(mail.outbox), 0)

    def test_stale_polling_alerts_admins_once(self):
        self.poll()

        self.assertEqual(check_polling_freshness(now=self.t0 + 20 * MIN), "stale")
        self.assertIsNone(check_polling_freshness(now=self.t0 + 25 * MIN))
        self.assertIsNone(check_polling_freshness(now=self.t0 + 10 * 60 * MIN))

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["ops@example.org"])
        self.assertIn("no successful feed poll", message.subject)
        self.assertTrue(message.subject.startswith(settings.EMAIL_SUBJECT_PREFIX))

    def test_reminds_every_24h_while_still_stale(self):
        self.poll()
        check_polling_freshness(now=self.t0 + 20 * MIN)

        self.assertIsNone(check_polling_freshness(now=self.t0 + 23 * 60 * MIN))
        self.assertEqual(check_polling_freshness(now=self.t0 + 20 * MIN + 24 * 60 * MIN), "reminder")

        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("Still stale", mail.outbox[1].subject)

    def test_recovery_is_announced_once(self):
        self.poll()
        check_polling_freshness(now=self.t0 + 20 * MIN)

        self.poll()  # a poll succeeds again
        later = timezone.now() + MIN
        self.assertEqual(check_polling_freshness(now=later), "recovered")
        self.assertIsNone(check_polling_freshness(now=later + 5 * MIN))

        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("Recovered", mail.outbox[1].subject)

    def test_alert_lists_the_latest_error_per_feed(self):
        self.poll()
        self.poll(ok=False, error="old error")
        self.poll(ok=False, error="Connection refused")

        check_polling_freshness(now=self.t0 + 20 * MIN)

        body = mail.outbox[0].body
        self.assertIn("Kenya Met", body)
        self.assertIn("Connection refused", body)
        self.assertNotIn("old error", body)

    def test_alert_with_no_failures_points_at_the_worker(self):
        self.poll()

        check_polling_freshness(now=self.t0 + 20 * MIN)

        self.assertIn("polls are not running at all", mail.outbox[0].body)

    def test_fresh_deploy_is_not_alerted_before_its_first_poll(self):
        self.assertIsNone(check_polling_freshness(now=self.t0 + 5 * MIN))
        self.assertEqual(check_polling_freshness(now=self.t0 + 20 * MIN), "stale")
        self.assertIn("No feed poll has ever succeeded", mail.outbox[0].body)

    def test_no_feed_authorities_means_nothing_to_check(self):
        self.authority.delete()

        self.assertIsNone(check_polling_freshness(now=self.t0 + 60 * MIN))
        self.assertEqual(len(mail.outbox), 0)

    def test_failed_send_is_retried_on_the_next_run(self):
        self.poll()

        with patch("capaggregator.ingestion.alerting.mail_admins", side_effect=OSError("smtp down")):
            self.assertIsNone(check_polling_freshness(now=self.t0 + 20 * MIN))

        self.assertEqual(check_polling_freshness(now=self.t0 + 25 * MIN), "stale")
        self.assertEqual(len(mail.outbox), 1)


class AdminsSettingTests(TestCase):
    def test_parses_name_email_pairs_and_bare_emails(self):
        from capaggregator.config.settings.base import parse_admins

        self.assertEqual(
            parse_admins("Ops:ops@example.org, jane@example.org ,"),
            [("Ops", "ops@example.org"), ("jane@example.org", "jane@example.org")],
        )
        self.assertEqual(parse_admins(""), [])

    def test_freshness_check_is_on_the_beat_schedule(self):
        by_task = {entry["task"]: entry["schedule"] for entry in settings.CELERY_BEAT_SCHEDULE.values()}

        self.assertEqual(by_task.get("capaggregator.ingestion.tasks.check_polling_freshness"), 300)
