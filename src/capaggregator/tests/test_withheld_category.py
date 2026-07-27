"""Every message we withhold arrives categorised.

Driven through the single ingestion entry point against real PostGIS, because
the category an operator ends up seeing is a property of the whole pipeline —
which check fires, which findings reach the report, and what gets denormalized
onto the row — not of the mapping in isolation.

One case per check that withholds a message: everything else publishes with its
findings recorded as defects (test_publish_with_defects). A message is only kept
back when storing it is impossible, or when publishing it would mean vouching
for content we cannot authenticate or would fork one hazard into two live
alerts.
"""

from unittest.mock import patch

from django.test import TestCase

from capaggregator.alerts.lineage import resolve
from capaggregator.alerts.models import Alert, AlertDefect
from capaggregator.ingestion import categories
from capaggregator.ingestion.models import QuarantinedMessage
from capaggregator.ingestion.tasks import ingest_raw_message
from capaggregator.ingestion.validators import check_polygons, validator_registry
from capaggregator.tests.cap_samples import NOT_WELL_FORMED_XML, cap_alert_xml
from capaggregator.tests.factories import create_source_authority


class WithheldCategoryTests(TestCase):
    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")

    def _withhold(self, xml, authority=None, unattributed=False):
        """Ingest `xml`, assert it was withheld, and return its withheld row."""
        authority_id = None if unattributed else (authority or self.authority).id
        result = ingest_raw_message(transport="manual", xml=xml, authority_id=authority_id)
        self.assertEqual(result["state"], "quarantined")
        return QuarantinedMessage.objects.get(raw_message_id=result["raw_id"])

    def test_not_well_formed_xml_is_schema(self):
        message = self._withhold(NOT_WELL_FORMED_XML)

        self.assertEqual(message.primary_category, categories.SCHEMA)

    def test_an_unreadable_sent_is_schema(self):
        # The one XSD-adjacent fault we still cannot publish through: without a
        # readable <sent> the CAP identity triple cannot be formed. Every other
        # schema violation now publishes with defects recorded
        # (test_publish_with_defects).
        message = self._withhold(cap_alert_xml(sent="not-a-date"))

        self.assertEqual(message.primary_category, categories.SCHEMA)

    def test_a_message_we_cannot_attribute_to_an_authority_is_identity(self):
        # No transport attribution at all: an Alert requires a non-null
        # authority, so this one cannot be stored. A sender merely outside a
        # registered authority's allow-list publishes with a defect instead.
        message = self._withhold(cap_alert_xml(), unattributed=True)

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

    def test_the_primary_category_is_the_most_upstream_of_several(self):
        # Two independent reasons to withhold one message: an unreadable <sent>
        # (schema) and no signature under an authority that requires one.
        strict = create_source_authority(
            name="Strict Met", country="ug", signature_policy="require",
            feed_url="https://strict.test/rss.xml",
        )

        message = self._withhold(cap_alert_xml(sent="not-a-date"), authority=strict)

        checks = {e["check"] for e in message.report["errors"]}
        self.assertTrue({"sent-parseable", "signature"} <= checks, "both findings must be recorded")
        self.assertEqual(message.primary_category, categories.SCHEMA)

    def test_the_category_is_fixed_at_creation_and_survives_dismissal(self):
        message = self._withhold(cap_alert_xml(), unattributed=True)

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

    def _crashes_on(self, result):
        defects = Alert.objects.get(id=result["alert_id"]).defects.all()
        return [d for d in defects if "crashed" in d.message]

    @patch("capaggregator.alerts.tasks.resolve_lineage")
    def test_a_crashing_validator_is_recorded_as_internal_not_as_its_own_check(self, _resolve):
        self._register_crashing_validator()

        result = ingest_raw_message(transport="manual", xml=cap_alert_xml(),
                                    authority_id=self.authority.id)

        # Still published — a crash in our rules must not withhold an alert.
        self.assertEqual(result["state"], "stored")
        crashes = self._crashes_on(result)
        self.assertEqual([d.check_name for d in crashes], [categories.CHECK_INTERNAL])
        self.assertEqual(crashes[0].category, categories.INTERNAL)
        self.assertIn("polygon-sanity", crashes[0].message, "the crashing rule must still be named")

    @patch("capaggregator.alerts.tasks.resolve_lineage")
    def test_a_crash_is_recorded_as_an_error_not_as_a_warning(self, _resolve):
        # A warning would disguise our bug as a minor conformance defect
        # belonging to the authority.
        self._register_crashing_validator()

        result = ingest_raw_message(transport="manual", xml=cap_alert_xml(),
                                    authority_id=self.authority.id)

        self.assertEqual([d.severity for d in self._crashes_on(result)], [AlertDefect.ERROR])

    @patch("capaggregator.alerts.tasks.resolve_lineage")
    def test_a_crash_costs_the_operator_nothing_but_that_rule(self, _resolve):
        self._register_crashing_validator()

        result = ingest_raw_message(transport="manual", xml=cap_alert_xml(expires=None),
                                    authority_id=self.authority.id)

        checks = {d.check_name for d in Alert.objects.get(id=result["alert_id"]).defects.all()}
        self.assertEqual(checks, {categories.CHECK_INTERNAL, "expires-required"},
                         "the other rules' findings must survive the crash")

    @patch("capaggregator.alerts.tasks.resolve_lineage")
    def test_the_signature_and_identity_checks_survive_a_crash(self, _resolve):
        # They now run against schema-invalid trees too, so they need the same
        # guard the semantic registry has — a bug in one must not abort ingestion.
        for target in ("_check_signature", "_check_sender"):
            with self.subTest(check=target), \
                 patch(f"capaggregator.ingestion.validators.{target}", side_effect=RuntimeError("boom")):
                result = ingest_raw_message(transport="manual", xml=cap_alert_xml(identifier=target),
                                            authority_id=self.authority.id)

                self.assertEqual(result["state"], "stored")
                self.assertEqual([d.category for d in self._crashes_on(result)], [categories.INTERNAL])
