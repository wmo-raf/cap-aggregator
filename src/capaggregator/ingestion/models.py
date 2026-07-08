from django.db import models
from django.utils.translation import gettext_lazy as _


class RawMessage(models.Model):
    """Every received CAP message, stored immutably before any processing.

    State machine:
      received → validated → stored
               ↘ quarantined
               ↘ duplicate
    """

    TRANSPORTS = (
        ("mqtt", "MQTT"),
        ("webhook", "Webhook"),
        ("poll", "Feed poll"),
        ("manual", "Manual upload"),
    )
    STATES = (
        ("received", _("Received")),
        ("validated", _("Validated")),
        ("stored", _("Stored")),
        ("quarantined", _("Quarantined")),
        ("duplicate", _("Duplicate")),
        ("failed", _("Failed")),
    )

    authority = models.ForeignKey("capagg_sources.SourceAuthority", null=True, blank=True,
                                  on_delete=models.SET_NULL, related_name="raw_messages")
    transport = models.CharField(max_length=10, choices=TRANSPORTS)
    topic = models.CharField(max_length=255, blank=True)
    xml = models.TextField()
    sha256 = models.CharField(max_length=64, unique=True)
    state = models.CharField(max_length=20, choices=STATES, default="received")
    received_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True, help_text=_("CAP <sent> — for latency metrics"))
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-received_at"]
        indexes = [
            models.Index(fields=["state", "received_at"]),
            models.Index(fields=["authority", "received_at"]),
        ]

    def __str__(self):
        return f"{self.transport}:{self.sha256[:12]} [{self.state}]"

    @property
    def ingest_latency(self):
        """Delay between when the alert was sent (CAP <sent>) and when we received
        it. None until the message has been parsed far enough to know its sent time."""
        if self.sent_at is None:
            return None
        return self.received_at - self.sent_at


class DeliveryReceipt(models.Model):
    """One row per arrival of a CAP message per transport — including duplicates.

    This is the transport-resolution mechanism: content is stored first-wins
    (CAP messages are immutable, so 'which transport won' never changes the
    data), and receipts turn later arrivals into telemetry:
      - MQTT vs poll latency per authority (health dashboard)
      - alerts that arrived ONLY via poll → the push transport silently failed
      - alerts that never arrived via the feed → the feed is broken/incomplete
    """

    authority = models.ForeignKey("capagg_sources.SourceAuthority", null=True, blank=True,
                                  on_delete=models.SET_NULL, related_name="delivery_receipts")
    transport = models.CharField(max_length=10, choices=RawMessage.TRANSPORTS)
    alert = models.ForeignKey("capagg_alerts.Alert", null=True, blank=True,
                              on_delete=models.CASCADE, related_name="delivery_receipts")
    raw_message = models.ForeignKey(RawMessage, null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="delivery_receipts")
    was_first = models.BooleanField(default=False, help_text=_("This arrival delivered the content"))
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at"]
        indexes = [
            models.Index(fields=["authority", "transport", "received_at"]),
            models.Index(fields=["alert", "transport"]),
        ]

    def __str__(self):
        return f"{self.transport} receipt for alert {self.alert_id} (first={self.was_first})"


class QuarantinedMessage(models.Model):
    """Invalid alerts are quarantined with a full validation report — never
    silently dropped. The report is surfaced to the source authority
    (data-quality feedback loop)."""

    STATUSES = (
        ("pending", _("Pending review")),
        ("notified", _("Authority notified")),
        ("resubmitted", _("Resubmitted")),
        ("dismissed", _("Dismissed")),
    )

    raw_message = models.OneToOneField(RawMessage, on_delete=models.CASCADE, related_name="quarantine")
    report = models.JSONField(default=dict, help_text=_("Per-check validation results"))
    status = models.CharField(max_length=20, choices=STATUSES, default="pending")
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"Quarantine #{self.pk} [{self.status}]"

    @property
    def report_summary(self) -> str:
        """Flatten the per-check report into legible text for the admin detail view."""
        lines = []
        for severity in ("errors", "warnings"):
            entries = self.report.get(severity) or []
            if entries:
                lines.append(f"{severity.capitalize()}:")
                lines += [f"  [{e.get('check', '?')}] {e.get('message', '')}" for e in entries]
        return "\n".join(lines) or _("No issues recorded")


class SourceEvent(models.Model):
    """Transport telemetry recorded beside ingestion (never part of it): every feed
    poll attempt (ok/failure), rejected webhook attempts, and MQTT consumer
    connect/disconnect events. Powers the health dashboard's red (poll failed) and
    faint-green (poll ok, no alerts) signals. Immutable, swept after 90 days."""

    authority = models.ForeignKey(
        "capagg_sources.SourceAuthority", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="source_events",
        help_text=_("Null for unattributable/global events (bad-token webhook, MQTT consumer)"),
    )
    transport = models.CharField(max_length=10, choices=RawMessage.TRANSPORTS)
    occurred_at = models.DateTimeField(auto_now_add=True)
    ok = models.BooleanField()
    error = models.TextField(blank=True)
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [models.Index(fields=["authority", "occurred_at"])]

    def __str__(self):
        return f"{self.transport} {'ok' if self.ok else 'fail'} @ {self.occurred_at:%Y-%m-%d %H:%M}"


# ---------------------------------------------------------------------------
# Task-ferry Job models (progress-tracked, pollable at /api/jobs/<id>/)
# ---------------------------------------------------------------------------

from task_ferry.models import Job  # noqa: E402


class CapBackfillJob(Job):
    """Operator-triggered bulk import of CAP XML — a single .xml file or a
    .zip archive of alerts (historical backfill, migration, testing).

    Each contained alert goes through the normal ingest pipeline, so dedup,
    validation, quarantine and lineage all apply."""

    authority = models.ForeignKey("capagg_sources.SourceAuthority", on_delete=models.CASCADE,
                                  related_name="backfill_jobs")
    file_path = models.CharField(max_length=500, help_text=_("Path to the uploaded .xml or .zip file"))
    alerts_found = models.IntegerField(default=0)
    alerts_stored = models.IntegerField(default=0)
    alerts_duplicate = models.IntegerField(default=0)
    alerts_quarantined = models.IntegerField(default=0)


class QuarantineRevalidationJob(Job):
    """Re-runs the full pipeline over pending quarantined messages — used after
    fixing an authority's registration (sender values, certificate) or after a
    validator rule change. Messages that now pass are stored; the rest get a
    fresh quarantine report."""

    authority = models.ForeignKey("capagg_sources.SourceAuthority", null=True, blank=True,
                                  on_delete=models.CASCADE, related_name="revalidation_jobs",
                                  help_text=_("Limit to one authority; empty = all"))
    messages_checked = models.IntegerField(default=0)
    messages_stored = models.IntegerField(default=0)
    messages_still_quarantined = models.IntegerField(default=0)
