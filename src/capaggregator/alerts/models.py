"""Core alert storage: every CAP message immutable (Alert/AlertInfo/AlertArea),
plus per-event-chain resolved state (EventChain/ResolvedAlert) that all tiles
and default queries serve. See docs/design.md §4–5."""

from django.contrib.gis.db import models as gis_models
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.utils.translation import gettext_lazy as _

MSG_TYPES = ("Alert", "Update", "Cancel", "Ack", "Error")
STATUSES = ("Actual", "Exercise", "System", "Test", "Draft")
URGENCIES = ("Immediate", "Expected", "Future", "Past", "Unknown")
SEVERITIES = ("Extreme", "Severe", "Moderate", "Minor", "Unknown")
CERTAINTIES = ("Observed", "Likely", "Possible", "Unlikely", "Unknown")

def _choices(values):
    return [(v, v) for v in values]


class Alert(models.Model):
    """One CAP <alert> message, stored immutably. Identity = (sender, identifier, sent)."""

    authority = models.ForeignKey("capagg_sources.SourceAuthority", on_delete=models.PROTECT,
                                  related_name="alerts")
    raw_message = models.ForeignKey("capagg_ingestion.RawMessage", on_delete=models.PROTECT,
                                    related_name="alerts")
    chain = models.ForeignKey("EventChain", null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="alerts")

    identifier = models.CharField(max_length=255)
    sender = models.CharField(max_length=255)
    sent = models.DateTimeField()
    msg_type = models.CharField(max_length=10, choices=_choices(MSG_TYPES))
    status = models.CharField(max_length=10, choices=_choices(STATUSES))
    scope = models.CharField(max_length=15)
    references = models.JSONField(default=list, blank=True,
                                  help_text=_("Parsed list of {sender, identifier, sent} triples"))
    note = models.TextField(blank=True)
    content_fingerprint = models.CharField(
        max_length=64, blank=True, db_index=True,
        help_text=_("sha256 of the CAP body excluding identifier/sent/effective — see "
                    "alerts.parser.content_fingerprint. Detects an upstream re-issue of the "
                    "same alert under a fresh identity triple."))
    signature_valid = models.BooleanField(null=True, blank=True)
    validation_warnings = models.JSONField(default=list, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["sender", "identifier", "sent"], name="uniq_cap_identity"),
        ]
        indexes = [models.Index(fields=["sent"]), models.Index(fields=["authority", "sent"])]
        ordering = ["-sent"]

    def __str__(self):
        return f"{self.identifier} ({self.msg_type}, {self.sent:%Y-%m-%d %H:%M})"


class AlertInfo(models.Model):
    """One CAP <info> block (one per language, typically)."""

    alert = models.ForeignKey(Alert, on_delete=models.CASCADE, related_name="infos")
    language = models.CharField(max_length=20, default="en-US")
    categories = ArrayField(models.CharField(max_length=20), default=list)
    event = models.CharField(max_length=255)
    response_types = ArrayField(models.CharField(max_length=20), default=list, blank=True)
    urgency = models.CharField(max_length=10, choices=_choices(URGENCIES))
    severity = models.CharField(max_length=10, choices=_choices(SEVERITIES))
    certainty = models.CharField(max_length=10, choices=_choices(CERTAINTIES))
    # Free-text CAP elements carry no length limit in the spec, and live feeds
    # exceed any guessed cap (700+ char percent-encoded <web> URLs, 550+ char
    # <audience> recipient lists) — TextField, never CharField
    audience = models.TextField(blank=True)
    onset = models.DateTimeField(null=True, blank=True)
    effective = models.DateTimeField(null=True, blank=True)
    expires = models.DateTimeField(null=True, blank=True)
    sender_name = models.CharField(max_length=255, blank=True)
    headline = models.TextField(blank=True)
    description = models.TextField(blank=True)
    instruction = models.TextField(blank=True)
    web = models.TextField(blank=True)
    contact = models.CharField(max_length=255, blank=True)
    parameters = models.JSONField(default=dict, blank=True)
    event_codes = models.JSONField(default=dict, blank=True)
    search_vector = SearchVectorField(null=True)

    class Meta:
        indexes = [GinIndex(fields=["search_vector"])]

    def __str__(self):
        return f"{self.event} [{self.language}]"


class AlertArea(gis_models.Model):
    """One CAP <area>. Circles are buffered server-side into polygons;
    geocode-only areas are resolved via the geocode registry."""

    info = models.ForeignKey(AlertInfo, on_delete=models.CASCADE, related_name="areas")
    area_desc = models.TextField()
    geom = gis_models.MultiPolygonField(srid=4326, null=True, blank=True)
    is_circle_derived = models.BooleanField(default=False)
    is_geocode_derived = models.BooleanField(default=False)
    geocodes = models.JSONField(default=dict, blank=True, help_text=_("scheme → [values]"))
    altitude = models.FloatField(null=True, blank=True)
    ceiling = models.FloatField(null=True, blank=True)

    def __str__(self):
        return self.area_desc


class EventChain(models.Model):
    """Groups Alert → Update → Cancel messages describing one event."""

    authority = models.ForeignKey("capagg_sources.SourceAuthority", on_delete=models.PROTECT,
                                  related_name="chains")
    first_alert = models.ForeignKey(Alert, on_delete=models.PROTECT, related_name="+")
    latest_alert = models.ForeignKey(Alert, on_delete=models.PROTECT, related_name="+")
    is_cancelled = models.BooleanField(default=False)
    incomplete_chain = models.BooleanField(
        default=False, help_text=_("An Update/Cancel referenced a message we never received"))
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Chain #{self.pk} ({self.latest_alert.identifier})"


class DanglingReference(models.Model):
    """Out-of-order arrival: an Update/Cancel referencing a not-yet-seen message.
    Re-resolved when (if) the referenced alert arrives."""

    alert = models.ForeignKey(Alert, on_delete=models.CASCADE, related_name="dangling_refs")
    ref_sender = models.CharField(max_length=255)
    ref_identifier = models.CharField(max_length=255)
    ref_sent = models.DateTimeField()
    resolved = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["ref_sender", "ref_identifier", "ref_sent", "resolved"])]


class ResolvedAlert(gis_models.Model):
    """Effective current state of one event chain — denormalized for tiles and search.
    Expiry is a query-time predicate (expires > t), which is what makes
    time-travel/animation work. This is the table capagg_alerts_tile() reads."""

    chain = models.OneToOneField(EventChain, on_delete=models.CASCADE, related_name="resolved")
    authority = models.ForeignKey("capagg_sources.SourceAuthority", on_delete=models.PROTECT,
                                  related_name="resolved_alerts")
    latest_alert = models.ForeignKey(Alert, on_delete=models.PROTECT, related_name="+")

    # Denormalized filter columns (from the latest alert's primary info block)
    msg_type = models.CharField(max_length=10)
    status = models.CharField(max_length=10)
    event = models.CharField(max_length=255)
    categories = ArrayField(models.CharField(max_length=20), default=list)
    urgency = models.CharField(max_length=10)
    severity = models.CharField(max_length=10)
    certainty = models.CharField(max_length=10)
    languages = ArrayField(models.CharField(max_length=20), default=list)
    headline = models.TextField(blank=True)
    onset = models.DateTimeField(null=True, blank=True)
    effective = models.DateTimeField(null=True, blank=True)
    expires = models.DateTimeField(null=True, blank=True)
    is_cancelled = models.BooleanField(default=False)

    # Country attribution: issuing authority's country + every country the geometry intersects
    countries = ArrayField(models.CharField(max_length=2), default=list)

    # Geometry at multiple simplification tolerances (precomputed for tile zoom ranges)
    geom = gis_models.MultiPolygonField(srid=4326, null=True, blank=True)
    geom_z8 = gis_models.MultiPolygonField(srid=4326, null=True, blank=True)
    geom_z5 = gis_models.MultiPolygonField(srid=4326, null=True, blank=True)
    centroid = gis_models.PointField(srid=4326, null=True, blank=True)

    modified = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["effective", "expires"]),
            models.Index(fields=["severity"]),
            GinIndex(fields=["categories"]),
            GinIndex(fields=["countries"]),
        ]

    def __str__(self):
        return f"{self.event} — {self.severity} ({', '.join(self.countries).upper()})"
