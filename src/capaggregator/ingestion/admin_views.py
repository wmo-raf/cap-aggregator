"""Wagtail admin view: manual CAP backfill upload.

Saves the upload under MEDIA_ROOT and starts the existing `cap_backfill`
task-ferry job; every contained alert runs through the normal ingestion pipeline.
"""

import uuid
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from task_ferry.handler import JobHandler
from wagtail.admin.auth import require_admin_access

from .forms import BackfillUploadForm


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
