"""Health dashboard 2/5: the status-matrix function — the per-authority, per-day
health computation the dashboard surfaces are built from."""

from datetime import datetime, timedelta
from datetime import timezone as dt_tz

from django.test import TestCase
from django.utils import timezone

from capaggregator.ingestion.health import build_health_matrix
from capaggregator.tests.factories import (
    create_alert_defect,
    create_cap_alert,
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

    def test_row_carries_the_authority_website_for_the_panels_external_link(self):
        create_source_authority(name="Kenya Met", website="https://meteo.go.ke")
        create_source_authority(name="Feedless Met", country="ug", feed_url="https://feeds.example.test/ug.atom")

        rows = {r["name"]: r for r in build_health_matrix(days=1)["authorities"]}

        self.assertEqual(rows["Kenya Met"]["website"], "https://meteo.go.ke")
        # No website and no cap-composer feed to derive one from: the panel renders no icon.
        self.assertEqual(rows["Feedless Met"]["website"], "")


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

    def test_defects_do_not_change_the_delivery_status_of_a_day(self):
        alert = create_cap_alert(self.authority)
        create_alert_defect(alert=alert, created=self.now)

        matrix = build_health_matrix(days=30, now=self.now)

        # The alert stored fine; only its conformance is at fault. Delivery
        # health is a separate axis and keeps its colour.
        self.assertEqual(self._today_status(matrix), "green")

    def test_defects_do_not_change_the_worst_first_ordering(self):
        broken = create_source_authority(name="Zed Met", country="zz", sender_values=["z@x"])
        create_source_event(broken, ok=False, transport="poll", occurred_at=self.now)
        # Kenya Met delivers perfectly and publishes 3 non-conformant alerts.
        for _ in range(3):
            create_alert_defect(alert=create_cap_alert(self.authority), created=self.now)

        matrix = build_health_matrix(days=30, now=self.now)

        # A day of defects must not sort an otherwise-healthy authority above a
        # failed poll — the two axes are independent.
        self.assertEqual([a["name"] for a in matrix["authorities"]], ["Zed Met", "Kenya Met"])

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


class HealthMatrixDefectTests(TestCase):
    """Conformance is a second, independent channel on the payload: a count per
    authority per day, carried alongside the delivery status rather than folded
    into it."""

    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")
        self.now = timezone.now()

    def _today_defects(self, matrix, name="Kenya Met"):
        row = next(a for a in matrix["authorities"] if a["name"] == name)
        return row["defects"][-1]

    def test_every_row_carries_one_defect_count_per_day(self):
        matrix = build_health_matrix(days=30, now=self.now)

        self.assertEqual(len(matrix["authorities"][0]["defects"]), 30)

    def test_a_day_with_defective_ingests_reports_a_count(self):
        alert = create_cap_alert(self.authority)
        create_alert_defect(alert=alert, check_name="polygon-sanity", created=self.now)
        create_alert_defect(alert=alert, check_name="xsd", created=self.now)

        matrix = build_health_matrix(days=30, now=self.now)

        # A count, not a boolean — an authority degrading is visible before it
        # is obviously broken.
        self.assertEqual(self._today_defects(matrix), 2)

    def test_a_day_with_no_defects_reports_no_count(self):
        create_raw_message(self.authority, state="stored", received_at=self.now)

        matrix = build_health_matrix(days=30, now=self.now)

        self.assertEqual(self._today_defects(matrix), 0)
        self.assertTrue(all(n == 0 for n in matrix["authorities"][0]["defects"]))

    def test_defects_are_attributed_to_the_publishing_authority_only(self):
        other = create_source_authority(name="Aba Met", country="aa", sender_values=["a@x"])
        create_alert_defect(alert=create_cap_alert(other), created=self.now)

        matrix = build_health_matrix(days=30, now=self.now)

        self.assertEqual(self._today_defects(matrix, "Aba Met"), 1)
        self.assertEqual(self._today_defects(matrix, "Kenya Met"), 0)

    def test_defects_are_bucketed_by_utc_day(self):
        now = datetime(2026, 7, 8, 12, 0, tzinfo=dt_tz.utc)
        create_alert_defect(alert=create_cap_alert(self.authority),
                            created=datetime(2026, 7, 8, 0, 30, tzinfo=dt_tz.utc))
        create_alert_defect(alert=create_cap_alert(self.authority),
                            created=datetime(2026, 7, 7, 23, 30, tzinfo=dt_tz.utc))

        matrix = build_health_matrix(days=30, now=now)

        defects = matrix["authorities"][0]["defects"]
        self.assertEqual(defects[-1], 1)
        self.assertEqual(defects[-2], 1)

    def test_defects_outside_the_window_are_not_counted(self):
        create_alert_defect(alert=create_cap_alert(self.authority),
                            created=self.now - timedelta(days=40))

        matrix = build_health_matrix(days=30, now=self.now)

        self.assertTrue(all(n == 0 for n in matrix["authorities"][0]["defects"]))

    def test_our_own_faults_are_not_counted_against_the_authority(self):
        alert = create_cap_alert(self.authority)
        create_alert_defect(alert=alert, check_name="polygon-sanity", created=self.now)
        # A crashing validator of ours is recorded as `internal`. The dashboard
        # is authority-facing reporting, so our bug must never show up as their
        # non-conformance.
        create_alert_defect(alert=alert, check_name="internal", created=self.now)

        matrix = build_health_matrix(days=30, now=self.now)

        self.assertEqual(self._today_defects(matrix), 1)

    def test_a_day_of_only_internal_faults_reports_no_count(self):
        create_alert_defect(alert=create_cap_alert(self.authority), check_name="internal", created=self.now)

        matrix = build_health_matrix(days=30, now=self.now)

        self.assertEqual(self._today_defects(matrix), 0)

    def test_single_authority_mode_carries_the_counts_too(self):
        create_alert_defect(alert=create_cap_alert(self.authority), created=self.now)

        matrix = build_health_matrix(days=30, now=self.now, authority_id=self.authority.id)

        self.assertEqual(self._today_defects(matrix), 1)
