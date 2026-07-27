"""Schema-invalid CAP publishes, with its findings recorded as defects.

The issuing authority already published these alerts on their own site and feed;
withholding one over a field we discard anyway makes us the only place the
warning is missing. So a message that fails XSD but can still be stored is
published, and every finding lands in the defect register instead of the
withheld one.

Driven through the single ingestion entry point against real PostGIS, because
the outcome an operator sees — what the message became, what defects it carries,
whether it reaches the read model — is a property of the whole pipeline, not of
the validator or the parser in isolation.
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from capaggregator.alerts.lineage import DEFAULT_ACTIVE_WINDOW, resolve
from capaggregator.alerts.models import Alert, AlertArea, AlertDefect, ResolvedAlert
from capaggregator.ingestion import categories
from capaggregator.ingestion.models import QuarantinedMessage, RawMessage
from capaggregator.ingestion.tasks import ingest_raw_message
from capaggregator.tests.cap_samples import cap_alert_xml
from capaggregator.tests.factories import create_source_authority

# 4 pairs, first != last — schema-valid, and the one warning-level finding real
# messages reach us with.
UNCLOSED_RING = "-1.30,36.80 -1.30,36.90 -1.20,36.90 -1.20,36.80"

# Enough to reach the verification branch and fail it, without minting a key
# pair: the check needs a <Signature> element and a configured certificate, and
# anything that does not verify against that certificate takes the same path.
UNVERIFIABLE_CERT_PEM = "-----BEGIN CERTIFICATE-----\nnot-a-real-certificate\n-----END CERTIFICATE-----"


def _with_bogus_signature(xml: str) -> str:
    return xml.replace("</alert>", '    <Signature xmlns="http://www.w3.org/2000/09/xmldsig#"/>\n</alert>')


def _cap_time(moment) -> str:
    """A CAP 1.2 dateTime: seconds resolution and an explicit offset, which is
    all the schema's pattern allows."""
    return moment.replace(microsecond=0).isoformat()


class PublishedWithDefectsTests(TestCase):
    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")

    def _store(self, xml):
        """Ingest `xml`, assert it published, and return the stored alert."""
        with patch("capaggregator.alerts.tasks.resolve_lineage.delay"):
            result = ingest_raw_message(transport="manual", xml=xml, authority_id=self.authority.id)
        self.assertEqual(result["state"], "stored", result)
        return Alert.objects.get(id=result["alert_id"])

    def _withhold(self, xml):
        """Ingest `xml`, assert nothing was published, and return the withheld row."""
        result = ingest_raw_message(transport="manual", xml=xml, authority_id=self.authority.id)
        self.assertNotEqual(result["state"], "stored", result)
        self.assertEqual(Alert.objects.count(), 0)
        return QuarantinedMessage.objects.get(raw_message_id=result["raw_id"])

    def test_a_schema_invalid_message_is_stored_with_its_schema_findings_as_defects(self):
        alert = self._store(cap_alert_xml(altitude="Zou"))

        schema_defects = alert.defects.filter(category=categories.SCHEMA)
        self.assertTrue(schema_defects.exists(), "the XSD findings must be on the register")
        self.assertEqual([d.check_name for d in schema_defects], ["xsd"] * schema_defects.count())
        self.assertEqual([d.severity for d in schema_defects], [AlertDefect.ERROR] * schema_defects.count())
        self.assertEqual(alert.defect_count, alert.defects.count())

    def test_a_region_name_in_altitude_publishes_with_the_discarded_value_recorded(self):
        # 72 of the current backlog's 77 XSD findings are exactly this: a
        # department name where the schema wants a decimal, in a field the
        # parser already throws away.
        alert = self._store(cap_alert_xml(altitude="Zou"))

        self.assertIsNone(AlertArea.objects.get(info__alert=alert).altitude, "parser discards it")
        self.assertTrue(any("Zou" in d.message for d in alert.defects.all()),
                        "the discarded value must be recoverable from the register")

    def test_a_sent_with_fractional_seconds_publishes_with_a_schema_defect(self):
        alert = self._store(cap_alert_xml(sent="2026-07-07T12:00:00.500+00:00"))

        self.assertEqual(alert.sent.isoformat(), "2026-07-07T12:00:00.500000+00:00")
        self.assertEqual([d.category for d in alert.defects.all()], [categories.SCHEMA])

    def test_a_published_defective_alert_is_resolved_and_served(self):
        now = timezone.now()
        alert = self._store(cap_alert_xml(
            altitude="Zou", sent=_cap_time(now - timedelta(hours=1)),
            expires=_cap_time(now + timedelta(hours=6)),
        ))

        resolve(alert)

        response = self.client.get(reverse("alert_search"))
        self.assertEqual(response.status_code, 200)
        features = response.json()["results"]["features"]
        self.assertEqual([f["properties"]["chain"] for f in features], [alert.chain_id])

    def test_the_published_read_model_carries_no_defect_information(self):
        # Tiles, search and the live stream all read ResolvedAlert. A defect is
        # not actionable for someone checking whether a flood warning covers
        # their district, and a caution badge would only nudge them to discount
        # a genuine warning.
        now = timezone.now()
        alert = self._store(cap_alert_xml(
            altitude="Zou", sent=_cap_time(now - timedelta(hours=1)),
            expires=_cap_time(now + timedelta(hours=6)),
        ))
        resolve(alert)

        response = self.client.get(reverse("alert_search"))

        self.assertNotIn("defect", response.content.decode().lower())
        self.assertEqual([f.name for f in ResolvedAlert._meta.get_fields() if "defect" in f.name], [])

    def test_an_unparseable_expires_publishes_under_the_default_active_window(self):
        alert = self._store(cap_alert_xml(expires="whenever"))

        self.assertIsNone(alert.infos.get().expires, "an unreadable expiry is stored as none")
        self.assertTrue(any(d.check_name == "datetime-format" and "whenever" in d.message
                            for d in alert.defects.all()))
        resolved = resolve(alert).resolved
        self.assertEqual(resolved.expires, resolved.effective + DEFAULT_ACTIVE_WINDOW)

    def test_over_length_identity_values_are_truncated_with_the_original_kept_verbatim(self):
        # Widening the columns would reward the malformation and change the
        # shape of the identity constraint; the raw message is where the
        # original survives.
        long_identifier = "I" * 300
        long_sender = "S" * 300
        # No allow-list, so the over-length <sender> is judged on storage alone
        # rather than on registration (attribution came from the transport).
        self.authority = create_source_authority(name="Open Met", country="ug", sender_values=[],
                                                 feed_url="https://open.test/rss.xml")

        alert = self._store(cap_alert_xml(identifier=long_identifier, sender=long_sender))

        self.assertEqual(alert.identifier, long_identifier[:255])
        self.assertEqual(alert.sender, long_sender[:255])
        truncations = alert.defects.filter(check_name="field-length")
        self.assertEqual({d.category for d in truncations}, {categories.CONTENT})
        self.assertEqual(truncations.count(), 2, "one finding per truncated field")
        self.assertIn(long_identifier, RawMessage.objects.get(pk=alert.raw_message_id).xml)


class WithheldOutcomeTests(TestCase):
    """What still cannot be published: a message we cannot store at all, and one
    whose storage failed for a reason that is ours rather than the publisher's."""

    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")

    def _ingest(self, xml):
        return ingest_raw_message(transport="manual", xml=xml, authority_id=self.authority.id)

    def test_a_sent_that_cannot_be_parsed_at_all_stays_withheld(self):
        result = self._ingest(cap_alert_xml(sent="not-a-date"))

        self.assertEqual(result["state"], "quarantined")
        self.assertEqual(Alert.objects.count(), 0)
        message = QuarantinedMessage.objects.get(raw_message_id=result["raw_id"])
        self.assertIn("sent-parseable", {e["check"] for e in message.report["errors"]})

    def test_an_unexpected_storage_failure_withholds_the_message_and_marks_it_failed(self):
        with patch("capaggregator.alerts.parser.parse_and_store", side_effect=RuntimeError("disk on fire")):
            result = self._ingest(cap_alert_xml())

        self.assertEqual(result["state"], "failed")
        self.assertEqual(Alert.objects.count(), 0)
        self.assertEqual(RawMessage.objects.get(pk=result["raw_id"]).state, "failed")
        message = QuarantinedMessage.objects.get(raw_message_id=result["raw_id"])
        self.assertEqual(message.primary_category, categories.INTERNAL)
        internal = [e for e in message.report["errors"] if e["check"] == categories.CHECK_INTERNAL]
        self.assertEqual(len(internal), 1)
        self.assertIn("disk on fire", internal[0]["message"])


class OneIngestionReportsEverythingTests(TestCase):
    """Validation no longer stops at the first layer that fails, so an operator
    learns about every defect in one ingestion rather than discovering the next
    one after each fix."""

    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")

    def test_a_schema_invalid_message_also_reports_its_semantic_findings(self):
        xml = cap_alert_xml(sent="2026-07-07T12:00:00.500+00:00", polygon=UNCLOSED_RING)

        with patch("capaggregator.alerts.tasks.resolve_lineage.delay"):
            result = ingest_raw_message(transport="manual", xml=xml, authority_id=self.authority.id)

        self.assertEqual(result["state"], "stored", result)
        defects = Alert.objects.get(id=result["alert_id"]).defects.all()
        self.assertEqual({d.check_name for d in defects}, {"xsd", "polygon-sanity"})

    def test_a_withheld_message_reports_its_other_findings_too(self):
        # An unsigned message still withholds under a `require` policy; the
        # schema and lineage faults that come with it are reported in the same
        # pass rather than waiting for the signature to be fixed first.
        strict = create_source_authority(name="Strict Met", country="ug", signature_policy="require",
                                         feed_url="https://strict.test/rss.xml")
        xml = cap_alert_xml(msg_type="Update", sent="2026-07-07T12:00:00.500+00:00")

        result = ingest_raw_message(transport="manual", xml=xml, authority_id=strict.id)

        self.assertEqual(result["state"], "quarantined")
        message = QuarantinedMessage.objects.get(raw_message_id=result["raw_id"])
        self.assertEqual({e["check"] for e in message.report["errors"]},
                         {"xsd", "signature", "references-required"})
        # Classified by why it was withheld: a defect we would have published
        # through must never read as the reason we refused.
        self.assertEqual(message.primary_category, categories.SIGNATURE)


class SemanticDefectsArePublishedTests(TestCase):
    """Everything the aggregator can store and serve around is published with
    its findings recorded — only content we cannot authenticate, cannot
    attribute, or that duplicates a live alert is kept back."""

    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met", sender_values=["registered@met.ke"])

    def _store(self, xml, authority=None):
        with patch("capaggregator.alerts.tasks.resolve_lineage.delay"):
            result = ingest_raw_message(transport="manual", xml=xml,
                                        authority_id=(authority or self.authority).id)
        self.assertEqual(result["state"], "stored", result)
        return Alert.objects.get(id=result["alert_id"])

    def _defect(self, alert, check):
        return alert.defects.get(check_name=check)

    def test_a_sender_outside_the_allow_list_publishes_with_an_identity_defect(self):
        # Attribution already came from the transport (MQTT topic, webhook
        # token, polled feed URL); the allow-list is our configuration, not a
        # statement about the content.
        alert = self._store(cap_alert_xml(sender="new-office@met.ke"))

        self.assertEqual(self._defect(alert, "sender").category, categories.IDENTITY)
        self.assertEqual(alert.sender, "new-office@met.ke")

    def test_an_update_without_references_publishes_with_a_lineage_defect(self):
        alert = self._store(cap_alert_xml(sender="registered@met.ke", msg_type="Update"))

        self.assertEqual(self._defect(alert, "references-required").category, categories.LINEAGE)

    def test_an_actual_public_alert_without_an_area_publishes_with_a_content_defect(self):
        alert = self._store(cap_alert_xml(sender="registered@met.ke", area=False))

        self.assertEqual(self._defect(alert, "area-for-actual-public").category, categories.CONTENT)

    def test_a_missing_expires_publishes_with_a_defect_recorded(self):
        alert = self._store(cap_alert_xml(sender="registered@met.ke", expires=None))

        self.assertEqual(self._defect(alert, "expires-required").category, categories.CONTENT)

    def test_one_malformed_polygon_among_several_keeps_the_shapes_that_parsed(self):
        good = "-1.30,36.80 -1.30,36.90 -1.20,36.90 -1.20,36.80 -1.30,36.80"
        malformed = "-1.30,36.80 not-a-pair -1.20,36.90 -1.30,36.80"

        alert = self._store(cap_alert_xml(sender="registered@met.ke", polygon=[good, malformed]))

        area = AlertArea.objects.get(info__alert=alert)
        self.assertIsNotNone(area.geom, "partial data loss must not become total data loss")
        self.assertEqual(area.geom.num_geom, 1, "only the shape that parsed is stored")
        self.assertEqual(self._defect(alert, "polygon-sanity").category, categories.CONTENT)

    def test_a_signature_failure_under_verify_if_present_publishes_with_a_signature_defect(self):
        signed = create_source_authority(
            name="Signing Met", country="ug", sender_values=[],
            signature_policy="verify_if_present", certificate_pem=UNVERIFIABLE_CERT_PEM,
            feed_url="https://signing.test/rss.xml",
        )

        alert = self._store(_with_bogus_signature(cap_alert_xml()), authority=signed)

        defect = self._defect(alert, "signature")
        self.assertEqual(defect.category, categories.SIGNATURE)
        self.assertEqual(defect.severity, AlertDefect.WARNING)

    def test_faults_in_several_categories_all_reach_the_register(self):
        alert = self._store(cap_alert_xml(
            sender="new-office@met.ke",      # identity
            msg_type="Update",               # lineage
            altitude="Zou",                  # schema
            expires=None,                    # content
        ))

        self.assertEqual(
            {d.category for d in alert.defects.all()},
            {categories.SCHEMA, categories.IDENTITY, categories.LINEAGE, categories.CONTENT},
        )
