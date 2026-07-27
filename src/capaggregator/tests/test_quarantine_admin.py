"""Phase B/4: the withheld-register admin surface — the list, its filters, and
the dismiss and re-validate actions. Smoke-level for the Wagtail plumbing; the
inspect view is covered in test_withheld_inspect and the re-validation behaviour
in test_quarantine_revalidation."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from django.contrib.auth.models import Permission

from capaggregator.ingestion.models import QuarantinedMessage, QuarantineRevalidationJob
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

    def test_register_is_read_only_even_for_a_superuser(self):
        message = create_quarantined_message(authority=self.authority)

        response = self.client.post(
            reverse("wagtailsnippets_capagg_ingestion_quarantinedmessage:edit", args=[message.pk]),
            {"status": "dismissed"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin/")
        message.refresh_from_db()
        self.assertEqual(message.status, "pending")

    def test_register_reads_as_withheld(self):
        response = self.client.get(reverse(self.LIST_URL_NAME))

        self.assertContains(response, "Withheld messages")


class WithheldStatusVocabularyTests(TestCase):
    def test_statuses_are_pending_and_dismissed_only(self):
        self.assertEqual([value for value, _label in QuarantinedMessage.STATUSES], ["pending", "dismissed"])


class BulkDismissTests(TestCase):
    """The register's only bulk path. Filter-awareness is the point: one
    authority's re-issues have to be clearable without touching anything else."""

    ACTION_URL = "/admin/bulk/capagg_ingestion/quarantinedmessage/dismiss/"

    def setUp(self):
        self.kenya = create_source_authority(name="Kenya Met")
        self.ghana = create_source_authority(name="Ghana Met", sender_values=["ghana@example.test"])
        self.user = get_user_model().objects.create_superuser("op", "op@example.test", "pw")
        self.client.force_login(self.user)

    def _reissue(self, authority):
        return create_quarantined_message(
            authority=authority,
            report={"errors": [{"check": "reissue", "message": "duplicate content"}], "warnings": []},
        )

    def test_selected_messages_are_dismissed_in_one_action(self):
        first = self._reissue(self.kenya)
        second = self._reissue(self.kenya)

        response = self.client.post(f"{self.ACTION_URL}?id={first.pk}&id={second.pk}")

        self.assertEqual(response.status_code, 302)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual([first.status, second.status], ["dismissed", "dismissed"])

    def test_select_all_in_listing_honours_the_authority_filter(self):
        mine = self._reissue(self.kenya)
        theirs = self._reissue(self.ghana)

        self.client.post(f"{self.ACTION_URL}?id=all&raw_message__authority={self.kenya.pk}")

        mine.refresh_from_db()
        theirs.refresh_from_db()
        self.assertEqual(mine.status, "dismissed")
        self.assertEqual(theirs.status, "pending")

    def test_select_all_in_listing_honours_the_category_filter(self):
        reissue = self._reissue(self.kenya)
        identity = create_quarantined_message(
            authority=self.kenya,
            report={"errors": [{"check": "sender", "message": "sender not registered"}], "warnings": []},
        )

        self.client.post(f"{self.ACTION_URL}?id=all&primary_category=reissue")

        reissue.refresh_from_db()
        identity.refresh_from_db()
        self.assertEqual(reissue.status, "dismissed")
        self.assertEqual(identity.status, "pending")

    def test_the_register_offers_the_dismiss_action(self):
        self._reissue(self.kenya)

        response = self.client.get(reverse("wagtailsnippets_capagg_ingestion_quarantinedmessage:list"))

        self.assertContains(response, self.ACTION_URL)

    def test_confirmation_page_lists_the_selected_messages(self):
        message = self._reissue(self.kenya)

        response = self.client.get(f"{self.ACTION_URL}?id={message.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dismiss")

    def test_unreadable_filters_dismiss_nothing(self):
        message = self._reissue(self.kenya)

        response = self.client.post(f"{self.ACTION_URL}?id=all&raw_message__authority=not-an-id")

        self.assertEqual(response.status_code, 302)  # nothing to dismiss, not an error
        message.refresh_from_db()
        self.assertEqual(message.status, "pending")

    def test_a_user_who_cannot_read_the_register_cannot_dismiss(self):
        message = self._reissue(self.kenya)
        clerk = get_user_model().objects.create_user("clerk", "clerk@example.test", "pw", is_staff=True)
        clerk.user_permissions.add(Permission.objects.get(codename="access_admin"))
        self.client.force_login(clerk)

        self.client.post(f"{self.ACTION_URL}?id={message.pk}")

        message.refresh_from_db()
        self.assertEqual(message.status, "pending")

    def test_bulk_dismiss_requires_login(self):
        message = self._reissue(self.kenya)
        self.client.logout()

        self.client.post(f"{self.ACTION_URL}?id={message.pk}")

        message.refresh_from_db()
        self.assertEqual(message.status, "pending")
