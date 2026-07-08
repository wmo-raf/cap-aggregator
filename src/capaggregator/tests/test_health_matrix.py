"""Health dashboard 2/5: the status-matrix function — the per-authority, per-day
health computation the dashboard surfaces are built from."""

from datetime import datetime
from datetime import timezone as dt_tz

from django.test import TestCase
from django.utils import timezone

from capaggregator.ingestion.health import build_health_matrix
from capaggregator.tests.factories import (
    create_raw_message,
    create_source_authority,
    create_source_event,
)


class HealthMatrixShapeTests(TestCase):
    def test_window_has_one_row_per_active_authority_and_a_status_per_day(self):
        create_source_authority(name="Kenya Met")

        matrix = build_health_matrix(days=30)

        self.assertEqual(len(matrix["days"]), 30)
        self.assertEqual(len(matrix["authorities"]), 1)
        row = matrix["authorities"][0]
        self.assertEqual(len(row["statuses"]), 30)
        self.assertTrue(all(s == "gray" for s in row["statuses"]))


class HealthMatrixStatusTests(TestCase):
    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")
        self.now = timezone.now()

    def _today_status(self, matrix):
        return matrix["authorities"][0]["statuses"][-1]

    def test_day_with_a_stored_message_is_green(self):
        create_raw_message(self.authority, state="stored", received_at=self.now)

        matrix = build_health_matrix(days=30, now=self.now)

        self.assertEqual(self._today_status(matrix), "green")

    def test_quarantine_beats_success_and_shows_orange(self):
        create_raw_message(self.authority, state="stored", received_at=self.now)
        create_raw_message(self.authority, state="quarantined", received_at=self.now)

        matrix = build_health_matrix(days=30, now=self.now)

        self.assertEqual(self._today_status(matrix), "orange")

    def test_failed_poll_beats_quarantine_and_shows_red(self):
        create_raw_message(self.authority, state="quarantined", received_at=self.now)
        create_source_event(self.authority, ok=False, transport="poll", occurred_at=self.now)

        matrix = build_health_matrix(days=30, now=self.now)

        self.assertEqual(self._today_status(matrix), "red")

    def test_day_is_red_when_the_latest_poll_failed(self):
        now = datetime(2026, 7, 8, 12, 0, tzinfo=dt_tz.utc)
        create_source_event(self.authority, ok=True, transport="poll",
                            occurred_at=datetime(2026, 7, 8, 9, 0, tzinfo=dt_tz.utc))
        create_source_event(self.authority, ok=False, transport="poll",
                            occurred_at=datetime(2026, 7, 8, 11, 0, tzinfo=dt_tz.utc))

        matrix = build_health_matrix(days=30, now=now)

        self.assertEqual(self._today_status(matrix), "red")

    def test_earlier_failure_recovered_by_a_later_poll_is_not_red(self):
        now = datetime(2026, 7, 8, 12, 0, tzinfo=dt_tz.utc)
        create_source_event(self.authority, ok=False, transport="poll",
                            occurred_at=datetime(2026, 7, 8, 9, 0, tzinfo=dt_tz.utc))
        create_source_event(self.authority, ok=True, transport="poll",
                            occurred_at=datetime(2026, 7, 8, 11, 0, tzinfo=dt_tz.utc))

        matrix = build_health_matrix(days=30, now=now)

        self.assertEqual(self._today_status(matrix), "alive")

    def test_successful_poll_with_no_alerts_is_alive(self):
        create_source_event(self.authority, ok=True, transport="poll", occurred_at=self.now)

        matrix = build_health_matrix(days=30, now=self.now)

        self.assertEqual(self._today_status(matrix), "alive")

    def test_duplicate_message_counts_as_green(self):
        create_raw_message(self.authority, state="duplicate", received_at=self.now)

        matrix = build_health_matrix(days=30, now=self.now)

        self.assertEqual(self._today_status(matrix), "green")

    def test_inactive_authority_is_excluded(self):
        create_source_authority(name="Retired Met", country="ug", sender_values=["u@x"], active=False)

        matrix = build_health_matrix(days=30, now=self.now)

        names = [a["name"] for a in matrix["authorities"]]
        self.assertNotIn("Retired Met", names)
        self.assertIn("Kenya Met", names)

    def test_authorities_are_ordered_worst_first(self):
        red = create_source_authority(name="Zed Met", country="zz", sender_values=["z@x"])
        orange = create_source_authority(name="Aba Met", country="aa", sender_values=["a@x"])
        create_source_event(red, ok=False, transport="poll", occurred_at=self.now)
        create_raw_message(orange, state="quarantined", received_at=self.now)
        # self.authority ("Kenya Met") is clean.

        matrix = build_health_matrix(days=30, now=self.now)

        self.assertEqual([a["name"] for a in matrix["authorities"]], ["Zed Met", "Aba Met", "Kenya Met"])

    def test_days_are_bucketed_in_utc(self):
        now = datetime(2026, 7, 8, 12, 0, tzinfo=dt_tz.utc)
        create_raw_message(self.authority, state="stored",
                           received_at=datetime(2026, 7, 8, 0, 30, tzinfo=dt_tz.utc))  # today 00:30 UTC
        create_raw_message(self.authority, state="quarantined",
                           received_at=datetime(2026, 7, 7, 23, 30, tzinfo=dt_tz.utc))  # yesterday 23:30 UTC

        matrix = build_health_matrix(days=30, now=now)

        statuses = matrix["authorities"][0]["statuses"]
        self.assertEqual(statuses[-1], "green")
        self.assertEqual(statuses[-2], "orange")
