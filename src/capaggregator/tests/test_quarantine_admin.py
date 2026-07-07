"""Phase B/4: the quarantine inbox admin surface — dismiss and re-validate actions
and the report-rendering detail view. Smoke-level for the Wagtail plumbing; the
re-validation behavior itself is covered in test_quarantine_revalidation."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from capaggregator.ingestion.models import QuarantineRevalidationJob
from capaggregator.tests.factories import create_quarantined_message, create_source_authority


class QuarantineActionTests(TestCase):
    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")
        self.user = get_user_model().objects.create_superuser("op", "op@example.test", "pw")
        self.client.force_login(self.user)

    def test_dismiss_moves_message_to_dismissed(self):
        message = create_quarantined_message(authority=self.authority)

        self.client.post(reverse("capagg_ingestion_quarantine_dismiss", args=[message.pk]))

        message.refresh_from_db()
        self.assertEqual(message.status, "dismissed")

    def test_revalidate_action_starts_a_job_and_redirects_to_progress(self):
        response = self.client.post(reverse("capagg_ingestion_quarantine_revalidate"))

        job = QuarantineRevalidationJob.objects.get()
        self.assertRedirects(response, f"/api/jobs/{job.id}/", fetch_redirect_response=False)


class QuarantineInboxTests(TestCase):
    LIST_URL_NAME = "wagtailsnippets_capagg_ingestion_quarantinedmessage:list"
    INSPECT_URL_NAME = "wagtailsnippets_capagg_ingestion_quarantinedmessage:inspect"

    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")
        self.user = get_user_model().objects.create_superuser("op", "op@example.test", "pw")
        self.client.force_login(self.user)

    def test_inbox_list_loads_and_filters_by_authority(self):
        create_quarantined_message(authority=self.authority)

        response = self.client.get(reverse(self.LIST_URL_NAME), {"raw_message__authority": self.authority.id})

        self.assertEqual(response.status_code, 200)

    def test_detail_view_renders_the_validation_report(self):
        report = {"errors": [{"check": "sender", "message": "DISTINCTIVE-REASON"}], "warnings": []}
        message = create_quarantined_message(authority=self.authority, report=report)

        response = self.client.get(reverse(self.INSPECT_URL_NAME, args=[message.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DISTINCTIVE-REASON")

    def test_inbox_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse(self.LIST_URL_NAME))

        self.assertEqual(response.status_code, 302)


class QuarantineReportSummaryTests(TestCase):
    def test_report_summary_lists_each_error_and_warning(self):
        report = {
            "errors": [{"check": "sender", "message": "sender not registered"}],
            "warnings": [{"check": "expires-required", "message": "missing expires"}],
        }
        message = create_quarantined_message(report=report)

        summary = message.report_summary

        self.assertIn("sender", summary)
        self.assertIn("sender not registered", summary)
        self.assertIn("expires-required", summary)
        self.assertIn("missing expires", summary)
