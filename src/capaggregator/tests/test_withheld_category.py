"""Every message we withhold arrives categorised.

Driven through the single ingestion entry point against real PostGIS, because
the category an operator ends up seeing is a property of the whole pipeline —
which check fires, which findings reach the report, and what gets denormalized
onto the row — not of the mapping in isolation.

One case per check that withholds a message today. This slice changes no
publication behaviour, so each case also asserts the message is still withheld.
"""

from unittest.mock import patch

from django.test import TestCase

from capaggregator.alerts.lineage import resolve
from capaggregator.alerts.models import Alert
from capaggregator.ingestion import categories
from capaggregator.ingestion.models import QuarantinedMessage
from capaggregator.ingestion.tasks import ingest_raw_message
from capaggregator.ingestion.validators import check_polygons, validator_registry
from capaggregator.tests.cap_samples import cap_alert_xml
from capaggregator.tests.factories import create_source_authority


class WithheldCategoryTests(TestCase):
    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")

    def _withhold(self, xml, authority=None):
        """Ingest `xml`, assert it was withheld, and return its withheld row."""
        result = ingest_raw_message(
            transport="manual", xml=xml, authority_id=(authority or self.authority).id
        )
        self.assertEqual(result["state"], "quarantined")
        return QuarantinedMessage.objects.get(raw_message_id=result["raw_id"])

    def test_not_well_formed_xml_is_schema(self):
        message = self._withhold("<alert>truncated")

        self.assertEqual(message.primary_category, categories.SCHEMA)

    def test_schema_invalid_xml_is_schema(self):
        # <msgType> is mandatory in CAP 1.2 — well-formed, but XSD-invalid.
        xml = cap_alert_xml().replace("    <msgType>Alert</msgType>\n", "")

        message = self._withhold(xml)

        self.assertEqual(message.primary_category, categories.SCHEMA)

    def test_unattributable_sender_is_identity(self):
        message = self._withhold(cap_alert_xml(sender="unregistered@x.test"))

        self.assertEqual(message.primary_category, categories.IDENTITY)

    def test_missing_signature_under_a_require_policy_is_signature(self):
        strict = create_source_authority(
            name="Strict Met", country="ug", signature_policy="require",
            feed_url="https://strict.test/rss.xml",
        )

        message = self._withhold(cap_alert_xml(), authority=strict)

        self.assertEqual(message.primary_category, categories.SIGNATURE)

    def test_an_upstream_reissue_is_reissue(self):
        first = ingest_raw_message(
            transport="manual", xml=cap_alert_xml(identifier="A", sent="2026-07-21T07:53:00+00:00"),
            authority_id=self.authority.id,
        )
        resolve(Alert.objects.get(id=first["alert_id"]))

        message = self._withhold(cap_alert_xml(identifier="B", sent="2026-07-21T07:54:00+00:00"))

        self.assertEqual(message.primary_category, categories.REISSUE)

    def test_an_update_without_references_is_lineage(self):
        message = self._withhold(cap_alert_xml(msg_type="Update"))

        self.assertEqual(message.primary_category, categories.LINEAGE)

    def test_an_actual_public_alert_without_an_area_is_content(self):
        message = self._withhold(cap_alert_xml(area=False))

        self.assertEqual(message.primary_category, categories.CONTENT)

    def test_a_malformed_polygon_is_content(self):
        message = self._withhold(cap_alert_xml(polygon="-1.30,36.80 -1.30,36.90 -1.30,36.80"))

        self.assertEqual(message.primary_category, categories.CONTENT)

    def test_the_primary_category_is_the_most_upstream_of_several(self):
        # Two independent faults in one message: an unregistered sender
        # (identity) and an Update with no <references> (lineage).
        message = self._withhold(cap_alert_xml(sender="unregistered@x.test", msg_type="Update"))

        checks = {e["check"] for e in message.report["errors"]}
        self.assertEqual(checks, {"sender", "references-required"}, "both findings must be recorded")
        self.assertEqual(message.primary_category, categories.IDENTITY)

    def test_the_category_is_fixed_at_creation_and_survives_dismissal(self):
        message = self._withhold(cap_alert_xml(sender="unregistered@x.test"))

        message.status = "dismissed"
        message.save()

        message.refresh_from_db()
        self.assertEqual(message.primary_category, categories.IDENTITY)


class InternalFaultTests(TestCase):
    """Our own faults are categorised as ours — never reported to an NMHS as a
    defect in their CAP."""

    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")

    def _register_crashing_validator(self):
        def explode(tree, raw, report):
            raise RuntimeError("boom")

        validator_registry.register("polygon-sanity")(explode)  # shadows a real rule
        self.addCleanup(validator_registry.register("polygon-sanity"), check_polygons)

    @patch("capaggregator.alerts.tasks.resolve_lineage")
    def test_a_crashing_validator_is_recorded_as_internal_not_as_its_own_check(self, _resolve):
        self._register_crashing_validator()

        result = ingest_raw_message(transport="manual", xml=cap_alert_xml(),
                                    authority_id=self.authority.id)

        # Still published — a crash in our rules must not withhold an alert.
        self.assertEqual(result["state"], "stored")
        warnings = Alert.objects.get(id=result["alert_id"]).validation_warnings
        crashes = [w for w in warnings if "crashed" in w["message"]]
        self.assertEqual([w["check"] for w in crashes], [categories.CHECK_INTERNAL])
        self.assertEqual(categories.category_for_check(crashes[0]["check"]), categories.INTERNAL)
        self.assertIn("polygon-sanity", crashes[0]["message"], "the crashing rule must still be named")
