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
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from task_ferry.handler import JobHandler
from wagtail.admin.auth import require_admin_access

from .forms import BackfillUploadForm
from .models import QuarantinedMessage


@require_admin_access
def health_dashboard_api(request):
    """Staff-gated JSON for the health panel + per-authority monitor strip."""
    from .health import build_health_matrix, mqtt_consumer_connected

    try:
        days = int(request.GET.get("days") or 30)
    except ValueError:
        days = 30
    days = max(1, min(days, 90))

    authority_id = request.GET.get("authority")
    matrix = build_health_matrix(days=days, authority_id=int(authority_id) if authority_id else None)
    matrix["mqtt_consumer_connected"] = mqtt_consumer_connected()
    return JsonResponse(matrix)


@require_admin_access
def authority_monitor(request, pk):
    """Per-authority ingestion monitor: header, activity strip, filtered message +
    transport-event tables, and quarantine backlog."""
    from django.urls import reverse

    from capaggregator.sources.models import SourceAuthority

    from .models import RawMessage, SourceEvent

    authority = get_object_or_404(SourceAuthority, pk=pk)

    state = request.GET.get("state") or ""
    transport = request.GET.get("transport") or ""
    since = request.GET.get("since") or ""

    messages_qs = RawMessage.objects.filter(authority=authority).prefetch_related("alerts__infos")
    events_qs = SourceEvent.objects.filter(authority=authority)
    if state:
        messages_qs = messages_qs.filter(state=state)
    if transport:
        messages_qs = messages_qs.filter(transport=transport)
        events_qs = events_qs.filter(transport=transport)
    if since:
        messages_qs = messages_qs.filter(received_at__date__gte=since)
        events_qs = events_qs.filter(occurred_at__date__gte=since)

    last_poll = SourceEvent.objects.filter(authority=authority, transport="poll").order_by("-occurred_at", "-id").first()

    context = {
        "authority": authority,
        "last_poll": last_poll,
        "quarantine_pending_count": QuarantinedMessage.objects.filter(
            raw_message__authority=authority, status__in=["pending", "notified"]
        ).count(),
        "recent_messages": messages_qs[:5],
        "recent_events": events_qs[:5],
        "health_api_url": reverse("capagg_ingestion_health_api") + f"?authority={authority.id}",
        "filters": {"state": state, "transport": transport, "since": since},
        "state_choices": RawMessage.STATES,
        "transport_choices": RawMessage.TRANSPORTS,
        "messages_all_url": reverse("wagtailsnippets_capagg_ingestion_rawmessage:list") + f"?authority={authority.id}",
        "events_all_url": reverse("wagtailsnippets_capagg_ingestion_sourceevent:list") + f"?authority={authority.id}",
        "quarantine_all_url": (
            reverse("wagtailsnippets_capagg_ingestion_quarantinedmessage:list")
            + f"?raw_message__authority={authority.id}"
        ),
    }
    return render(request, "capagg_ingestion/authority_monitor.html", context)


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
