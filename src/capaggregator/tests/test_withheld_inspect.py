"""Reading a withheld message in the admin.

The operator's job here is to work out what is wrong with a message and tell the
authority that published it, so the view is asserted the way they use it: the
provenance is to hand, the findings are legible and name their check, a finding
that references another alert is followed rather than trusted, and the whole
thing can be copied into an email.

Driven over the Wagtail admin with the test client — the same HTTP surface the
operator gets.
"""

from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from capaggregator import ingestion
from capaggregator.tests.cap_samples import cap_alert_xml
from capaggregator.tests.factories import (
    create_cap_alert,
    create_event_chain,
    create_quarantined_message,
    create_source_authority,
)

INSPECT_URL_NAME = "wagtailsnippets_capagg_ingestion_quarantinedmessage:inspect"
ALERT_INSPECT_URL_NAME = "wagtailsnippets_capagg_alerts_alert:inspect"
RAW_INSPECT_URL_NAME = "wagtailsnippets_capagg_ingestion_rawmessage:inspect"


def reissue_report(alert, chain_id=None):
    return {
        "errors": [{
            "check": "reissue",
            "message": f"content identical to alert #{alert.pk} ({alert.identifier})",
            "context": {"alert": alert.pk, "chain": chain_id if chain_id is not None else alert.chain_id},
        }],
        "warnings": [],
    }


class WithheldInspectViewTests(TestCase):
    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met Department")
        self.user = get_user_model().objects.create_superuser("op", "op@example.test", "pw")
        self.client.force_login(self.user)

    def _inspect(self, message):
        response = self.client.get(reverse(INSPECT_URL_NAME, args=[message.pk]))
        self.assertEqual(response.status_code, 200)
        return response

    def test_the_provenance_header_carries_the_context_for_the_findings(self):
        message = create_quarantined_message(authority=self.authority, transport="mqtt",
                                             topic="cap/in/ke/kenya-met")

        response = self._inspect(message)

        self.assertContains(response, "Kenya Met Department")
        self.assertContains(response, "cap/in/ke/kenya-met")
        self.assertContains(response, message.raw_message.sha256)
        self.assertContains(response, "MQTT")

    def test_a_category_badge_names_what_the_operator_is_looking_at(self):
        message = create_quarantined_message(
            authority=self.authority,
            report={"errors": [{"check": "reissue", "message": "duplicate content"}], "warnings": []},
        )

        response = self._inspect(message)

        self.assertContains(response, "capagg-category-badge")
        self.assertContains(response, "Re-issue")

    def test_one_findings_list_with_errors_before_warnings_naming_each_check(self):
        message = create_quarantined_message(authority=self.authority, report={
            "errors": [{"check": "reissue", "message": "THE-ERROR"}],
            "warnings": [{"check": "expires-required", "message": "THE-WARNING"}],
        })

        content = self._inspect(message).content.decode()

        self.assertIn("reissue", content)
        self.assertIn("expires-required", content)
        self.assertLess(content.index("THE-ERROR"), content.index("THE-WARNING"),
                        "the blocking problem must be the first thing read")

    def test_the_raw_xml_is_collapsed_and_line_numbered(self):
        message = create_quarantined_message(authority=self.authority, xml=cap_alert_xml())

        content = self._inspect(message).content.decode()

        self.assertIn("capagg-xml", content)
        self.assertNotIn("<details open", content, "hundreds of lines would bury the findings")
        self.assertIn("capagg-xml-line", content)

    def test_a_finding_with_a_line_expands_the_xml_and_highlights_that_line(self):
        xml = cap_alert_xml()
        line = next(n for n, text in enumerate(xml.splitlines(), start=1) if "<sent>" in text)
        message = create_quarantined_message(authority=self.authority, xml=xml, report={
            "errors": [{"check": "xsd", "message": "bad sent", "context": {"line": line}}],
            "warnings": [],
        })

        content = self._inspect(message).content.decode()

        self.assertIn("<details open", content)
        self.assertIn(f'id="capagg-xml-line-{line}"', content)
        self.assertIn("capagg-xml-line--flagged", content)

    def test_a_reissue_finding_links_to_the_referenced_alerts_admin_view(self):
        # Confirming the duplication means reading the other alert, not trusting
        # the message text — and without leaving the admin mid-investigation.
        chain = create_event_chain(self.authority)
        alert = chain.latest_alert
        message = create_quarantined_message(authority=self.authority, report=reissue_report(alert))

        response = self._inspect(message)

        self.assertContains(response, reverse(ALERT_INSPECT_URL_NAME, args=[alert.pk]))

    def test_the_link_degrades_to_the_raw_message_when_the_alert_has_no_chain(self):
        alert = create_cap_alert(self.authority)  # stored, never resolved
        message = create_quarantined_message(authority=self.authority, report=reissue_report(alert))

        response = self._inspect(message)

        self.assertContains(response, reverse(RAW_INSPECT_URL_NAME, args=[alert.raw_message_id]))

    def test_a_copy_report_affordance_carries_the_whole_report(self):
        message = create_quarantined_message(authority=self.authority, report={
            "errors": [{"check": "reissue", "message": "DISTINCTIVE-REASON"}], "warnings": [],
        })

        response = self._inspect(message)

        self.assertContains(response, "capagg-copy-report")
        self.assertContains(response, "DISTINCTIVE-REASON")

    def test_the_dismiss_and_revalidate_actions_are_still_offered(self):
        message = create_quarantined_message(authority=self.authority)

        response = self._inspect(message)

        self.assertContains(response, reverse("capagg_ingestion_quarantine_dismiss", args=[message.pk]))
        self.assertContains(response, reverse("capagg_ingestion_quarantine_revalidate"))

    def test_the_template_carries_no_inline_styles(self):
        # Asserted against the template source, not the response: Wagtail's own
        # admin chrome emits inline styles we neither own nor control.
        source = (Path(ingestion.__file__).parent
                  / "templates" / "capagg_ingestion" / "quarantine_inspect.html").read_text()

        self.assertNotIn(' style="', source, "styling belongs in the extra_css block")


class CopyReportTests(TestCase):
    """The copy-report text is what gets pasted into an email to an NMHS, so it
    has to stand on its own: who sent what, when, and everything wrong with it."""

    def test_the_report_names_the_provenance_the_identifiers_and_every_finding(self):
        authority = create_source_authority(name="Benin Met")
        message = create_quarantined_message(authority=authority, xml=cap_alert_xml(identifier="BJ-0001"), report={
            "errors": [{"check": "reissue", "message": "identical to an alert already live"}],
            "warnings": [{"check": "expires-required", "message": "info block without <expires>"}],
        })

        report = message.copy_report()

        self.assertIn("Benin Met", report)
        self.assertIn(message.raw_message.sha256, report)
        self.assertIn("BJ-0001", report, "the CAP identifier the authority will recognise")
        self.assertIn("[reissue]", report)
        self.assertIn("identical to an alert already live", report)
        self.assertIn("[expires-required]", report)
        self.assertIn("info block without <expires>", report)
