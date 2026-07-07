"""Phase B/1: ingestion must run unattended — the feed-poll dispatcher and the
recovery sweep are registered on the Celery beat schedule a fresh deploy loads."""

from django.conf import settings
from django.test import SimpleTestCase


class BeatScheduleTests(SimpleTestCase):
    def test_ingestion_periodic_tasks_are_registered(self):
        by_task = {entry["task"]: entry["schedule"] for entry in settings.CELERY_BEAT_SCHEDULE.values()}

        self.assertEqual(by_task.get("capaggregator.ingestion.tasks.poll_all_feeds"), 60)
        self.assertEqual(by_task.get("capaggregator.ingestion.tasks.sweep_unprocessed"), 300)
