"""Wagtail admin views for the ingestion app.

- Manual CAP backfill upload: stores an uploaded .xml/.zip under MEDIA_ROOT and
  starts the `cap_backfill` job.
- Quarantine actions: re-run validation over pending messages (bulk), and dismiss
  a single quarantined message.
"""

import uuid
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from task_ferry.handler import JobHandler
from wagtail.admin.auth import require_admin_access

from .forms import BackfillUploadForm
from .models import QuarantinedMessage


def _store_upload(upload) -> Path:
    """Persist an uploaded file to a unique path under MEDIA_ROOT/backfills/."""
    target_dir = Path(settings.MEDIA_ROOT) / "backfills" / uuid.uuid4().hex
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / upload.name
    with open(target, "wb") as fh:
        for chunk in upload.chunks():
            fh.write(chunk)
    return target


@require_admin_access
def backfill_upload(request):
    if request.method == "POST":
        form = BackfillUploadForm(request.POST, request.FILES)
        if form.is_valid():
            path = _store_upload(form.cleaned_data["file"])
            job = JobHandler.create_and_start(
                request.user,
                "cap_backfill",
                authority_id=form.cleaned_data["authority"].id,
                file_path=str(path),
            )
            messages.success(
                request, _("Backfill started. Track progress at /api/jobs/%(id)s/.") % {"id": job.id}
            )
            return redirect(f"/api/jobs/{job.id}/")
    else:
        form = BackfillUploadForm()

    return render(request, "capagg_ingestion/backfill_upload.html", {"form": form})


@require_admin_access
@require_POST
def quarantine_revalidate(request):
    """Start the bulk re-validation sweep over all pending/notified messages."""
    job = JobHandler.create_and_start(request.user, "quarantine_revalidation")
    messages.success(
        request, _("Re-validation started. Track progress at /api/jobs/%(id)s/.") % {"id": job.id}
    )
    return redirect(f"/api/jobs/{job.id}/")


@require_admin_access
@require_POST
def quarantine_dismiss(request, pk):
    message = get_object_or_404(QuarantinedMessage, pk=pk)
    message.status = "dismissed"
    message.save(update_fields=["status", "modified"])
    messages.success(request, _("Quarantined message dismissed."))
    return redirect("/admin/snippets/capagg_ingestion/quarantinedmessage/")
