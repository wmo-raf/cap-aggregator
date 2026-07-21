"""An upstream publisher that re-serializes an already-disseminated alert with a
fresh <sent> must not fork it into a second live alert.

Observed in production against cap-composer: `CapAlertPage.save()` re-stamps
`sent = now()` on every full save, and the post-publish multimedia task saves the
page three more times. When one of those saves crosses a minute boundary, `sent`
moves — and because `<identifier>` is derived from `sent` whenever the authority
has a WMO OID configured, the identifier moves with it. Two consecutive feed
polls then fetch what look like two unrelated alerts for the same hazard.
"""

from datetime import datetime

from django.test import TestCase, override_settings

from capaggregator.alerts.lineage import resolve
from capaggregator.alerts.models import Alert, ResolvedAlert
from capaggregator.alerts.parser import content_fingerprint
from capaggregator.ingestion.models import QuarantinedMessage
from capaggregator.ingestion.tasks import ingest_raw_message
from capaggregator.tests.cap_samples import cap_alert_xml
from capaggregator.tests.factories import create_source_authority

OID_PREFIX = "2.49.0.0.404.0"


def oid_for(sent_iso: str) -> str:
    """Mirror cap-composer's format_date_to_oid(): Y.M.D.h.m.s, unpadded."""
    d = datetime.fromisoformat(sent_iso)
    return f"urn:oid:{OID_PREFIX}.{d.year}.{d.month}.{d.day}.{d.hour}.{d.minute}.{d.second}"


class ReissueDetectionTests(TestCase):
    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")

    def _ingest(self, sent, **kw):
        kw.setdefault("identifier", oid_for(sent))
        result = ingest_raw_message(
            transport="poll", xml=cap_alert_xml(sent=sent, **kw), authority_id=self.authority.id
        )
        if result.get("alert_id"):
            resolve(Alert.objects.get(id=result["alert_id"]))
        return result

    def test_resave_crossing_a_minute_boundary_is_quarantined_not_duplicated(self):
        self._ingest("2026-07-21T07:53:00+00:00")
        result = self._ingest("2026-07-21T07:54:00+00:00")

        self.assertEqual(result["state"], "quarantined")
        self.assertEqual(ResolvedAlert.objects.count(), 1, "the re-issue must not become a second live alert")

        report = QuarantinedMessage.objects.get().report
        messages = [e["message"] for e in report["errors"] if e["check"] == "reissue"]
        self.assertEqual(len(messages), 1)
        # The operator needs to see which alert it collided with, not just that it did
        self.assertIn("urn:oid:2.49.0.0.404.0.2026.7.21.7.53.0", messages[0])

    def test_a_genuine_update_still_supersedes(self):
        """<references> means deliberate supersession — lineage's job, not ours."""
        self._ingest("2026-07-21T07:53:00+00:00")
        result = self._ingest(
            "2026-07-21T07:54:00+00:00",
            msg_type="Update",
            references=f"sender@example.test,{oid_for('2026-07-21T07:53:00+00:00')},2026-07-21T07:53:00+00:00",
        )

        self.assertEqual(result["state"], "stored")
        self.assertEqual(ResolvedAlert.objects.count(), 1, "the Update joins the existing chain")

    def test_distinct_alerts_from_one_authority_are_untouched(self):
        """Same authority, different hazard — must not collide."""
        self._ingest("2026-07-21T07:53:00+00:00")
        result = self._ingest("2026-07-21T07:54:00+00:00", headline="Locust swarm approaching")

        self.assertEqual(result["state"], "stored")
        self.assertEqual(ResolvedAlert.objects.count(), 2)

    @override_settings(CAP_REISSUE_WINDOW_MINUTES=60)
    def test_identical_content_outside_the_window_is_a_new_alert(self):
        """An authority re-issuing the same bulletin the next day is not a re-issue."""
        self._ingest("2026-07-21T07:53:00+00:00")
        result = self._ingest("2026-07-22T07:53:00+00:00")

        self.assertEqual(result["state"], "stored")
        self.assertEqual(ResolvedAlert.objects.count(), 2)

    def test_same_content_from_a_different_authority_is_untouched(self):
        other = create_source_authority(name="Uganda Met", country="ug", sender_values=[])
        self._ingest("2026-07-21T07:53:00+00:00")
        result = ingest_raw_message(
            transport="poll",
            xml=cap_alert_xml(sent="2026-07-21T07:54:00+00:00", identifier="UG-1"),
            authority_id=other.id,
        )

        self.assertEqual(result["state"], "stored")


class ContentFingerprintTests(TestCase):
    def test_volatile_elements_do_not_change_the_fingerprint(self):
        base = cap_alert_xml(identifier="A", sent="2026-07-21T07:53:00+00:00")
        moved = cap_alert_xml(identifier="B", sent="2026-07-21T07:54:00+00:00")

        self.assertEqual(content_fingerprint(base), content_fingerprint(moved))

    def test_content_changes_do_change_the_fingerprint(self):
        base = cap_alert_xml(headline="Severe flooding expected")
        other = cap_alert_xml(headline="Locust swarm approaching")

        self.assertNotEqual(content_fingerprint(base), content_fingerprint(other))

    def test_expiry_is_part_of_the_fingerprint(self):
        """<expires> is author-set and bounds the alert — two bulletins with the
        same text but different validity windows are different alerts."""
        base = cap_alert_xml(expires="2026-07-08T12:00:00+00:00")
        other = cap_alert_xml(expires="2026-07-09T12:00:00+00:00")

        self.assertNotEqual(content_fingerprint(base), content_fingerprint(other))

    def test_whitespace_and_element_order_do_not_change_the_fingerprint(self):
        pretty = cap_alert_xml()
        compact = pretty.replace("\n    ", "\n").replace("\n        ", "\n")

        self.assertEqual(content_fingerprint(pretty), content_fingerprint(compact))

    def test_unparseable_xml_yields_no_fingerprint(self):
        self.assertEqual(content_fingerprint("<alert>truncated"), "")
