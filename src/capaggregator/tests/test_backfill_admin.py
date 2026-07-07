"""Phase B/3: the admin backfill upload action — a staff-gated page that accepts a
CAP .xml/.zip and starts a backfill job. Smoke-level: the view loads and the
upload wires through to a job (job-type behavior is covered in test_backfill_job)."""

import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from capaggregator.ingestion.models import CapBackfillJob
from capaggregator.tests.cap_samples import cap_alert_xml
from capaggregator.tests.factories import create_source_authority


class BackfillAdminTests(TestCase):
    def setUp(self):
        self.authority = create_source_authority(name="Kenya Met")
        self.user = get_user_model().objects.create_superuser("op", "op@example.test", "pw")
        self.client.force_login(self.user)

    def test_upload_page_loads_for_staff(self):
        response = self.client.get(reverse("capagg_ingestion_backfill_upload"))

        self.assertEqual(response.status_code, 200)

    def test_upload_starts_backfill_job_and_redirects_to_progress(self):
        upload = SimpleUploadedFile("alert.xml", cap_alert_xml().encode(), content_type="application/xml")

        with override_settings(MEDIA_ROOT=tempfile.mkdtemp()):
            response = self.client.post(
                reverse("capagg_ingestion_backfill_upload"),
                {"authority": self.authority.id, "file": upload},
            )

        job = CapBackfillJob.objects.get()
        self.assertEqual(job.authority_id, self.authority.id)
        self.assertRedirects(response, f"/api/jobs/{job.id}/", fetch_redirect_response=False)
