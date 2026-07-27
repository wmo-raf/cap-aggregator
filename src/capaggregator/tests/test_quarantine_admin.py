"""Phase B/4: the withheld-register admin surface — the list, its filters, and
the dismiss and re-validate actions. Smoke-level for the Wagtail plumbing; the
inspect view is covered in test_withheld_inspect and the re-validation behaviour
in test_quarantine_revalidation."""

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

    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")
        self.user = get_user_model().objects.create_superuser("op", "op@example.test", "pw")
        self.client.force_login(self.user)

    def test_inbox_list_loads_and_filters_by_authority(self):
        create_quarantined_message(authority=self.authority)

        response = self.client.get(reverse(self.LIST_URL_NAME), {"raw_message__authority": self.authority.id})

        self.assertEqual(response.status_code, 200)

    def test_inbox_list_shows_the_category_column(self):
        create_quarantined_message(
            authority=self.authority,
            report={"errors": [{"check": "reissue", "message": "duplicate content"}], "warnings": []},
        )

        response = self.client.get(reverse(self.LIST_URL_NAME))

        self.assertContains(response, "Category")
        self.assertContains(response, "Re-issue")

    def test_inbox_list_filters_by_category(self):
        create_quarantined_message(
            authority=self.authority,
            report={"errors": [{"check": "reissue", "message": "duplicate content"}], "warnings": []},
        )
        create_quarantined_message(
            authority=self.authority,
            report={"errors": [{"check": "sender", "message": "SENDER-PROBLEM"}], "warnings": []},
        )

        response = self.client.get(reverse(self.LIST_URL_NAME), {"primary_category": "identity"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual([m.primary_category for m in response.context["object_list"]], ["identity"])

    def test_inbox_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse(self.LIST_URL_NAME))

        self.assertEqual(response.status_code, 302)
