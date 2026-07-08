"""Health dashboard 1/5: every feed poll attempt records a SourceEvent — the
telemetry the dashboard's red (poll failed) and faint-green (alive but quiet)
signals are built from."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from capaggregator.ingestion.models import SourceEvent
from capaggregator.ingestion.tasks import poll_feed, purge_old_source_events
from capaggregator.tests.factories import create_source_authority


class PollEventTests(TestCase):
    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")

    @patch("capaggregator.sources.feeds.fetch_feed", return_value=([], True))
    def test_successful_poll_records_an_ok_event(self, _fetch_feed):
        poll_feed(self.authority.id)

        event = SourceEvent.objects.get()
        self.assertEqual(event.authority_id, self.authority.id)
        self.assertEqual(event.transport, "poll")
        self.assertTrue(event.ok)
        self.assertIn("entries_fetched", event.detail)

    @patch("capaggregator.sources.feeds.fetch_feed", side_effect=ConnectionError("feed unreachable: 503"))
    def test_failed_poll_records_an_error_event(self, _fetch_feed):
        poll_feed(self.authority.id)

        event = SourceEvent.objects.get()
        self.assertEqual(event.authority_id, self.authority.id)
        self.assertEqual(event.transport, "poll")
        self.assertFalse(event.ok)
        self.assertIn("feed unreachable: 503", event.error)


class SourceEventRetentionTests(TestCase):
    def test_purge_removes_events_older_than_90_days_and_keeps_newer(self):
        authority = create_source_authority(name="Kenya Met")
        old = SourceEvent.objects.create(authority=authority, transport="poll", ok=True)
        recent = SourceEvent.objects.create(authority=authority, transport="poll", ok=True)
        # occurred_at is auto_now_add, so backdate the old one past the cutoff.
        SourceEvent.objects.filter(pk=old.pk).update(occurred_at=timezone.now() - timedelta(days=91))

        purge_old_source_events()

        self.assertFalse(SourceEvent.objects.filter(pk=old.pk).exists())
        self.assertTrue(SourceEvent.objects.filter(pk=recent.pk).exists())


class RetentionScheduleTests(TestCase):
    def test_retention_task_is_registered_daily(self):
        from django.conf import settings

        by_task = {entry["task"]: entry["schedule"] for entry in settings.CELERY_BEAT_SCHEDULE.values()}
        self.assertEqual(by_task.get("capaggregator.ingestion.tasks.purge_old_source_events"), 86400)


class SourceEventAdminTests(TestCase):
    LIST_URL_NAME = "wagtailsnippets_capagg_ingestion_sourceevent:list"

    def setUp(self):
        from django.contrib.auth import get_user_model

        self.authority = create_source_authority(name="Kenya Met")
        self.user = get_user_model().objects.create_superuser("op", "op@example.test", "pw")
        self.client.force_login(self.user)

    def test_list_loads_and_filters_for_staff(self):
        from django.urls import reverse

        SourceEvent.objects.create(authority=self.authority, transport="poll", ok=True)

        response = self.client.get(reverse(self.LIST_URL_NAME), {"transport": "poll"})

        self.assertEqual(response.status_code, 200)

    def test_source_events_cannot_be_edited(self):
        from django.urls import reverse

        event = SourceEvent.objects.create(authority=self.authority, transport="poll", ok=True)

        response = self.client.get(reverse("wagtailsnippets_capagg_ingestion_sourceevent:edit", args=[event.pk]))

        self.assertNotEqual(response.status_code, 200)
