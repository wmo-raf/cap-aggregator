import secrets

from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django_countries.fields import CountryField
from wagtail.admin.panels import FieldPanel, MultiFieldPanel


class SourceAuthority(models.Model):
    """A registered alerting authority — typically one cap-composer instance.

    Transport model:
      - REQUIRED: a CAP RSS/ATOM feed URL (the CAP-standard baseline; type
        declared or autodiscovered). Always polled — slow reconcile sweep when
        push is healthy, fast polling otherwise.
      - OPTIONAL: MQTT (preferred, near-real-time) and/or webhook push.
      - Duplicate arrivals across transports are resolved first-wins on the CAP
        identity triple; every arrival is logged as a DeliveryReceipt.

    Onboarding flow:
      1. Create this record (name, country, CAP sender values, feed URL).
      2. Optionally issue MQTT credentials (admin action → issue_mqtt_credentials()).
         Broker auth syncs automatically on save (signal → Celery task → broker
         self-reloads); `capagg sync_mosquitto` exists only for bootstrap/repair.
      3. The NMHS configures the issued host/credentials/topic in cap-composer's
         "MQTT Brokers" settings (plain broker, is_wis2box unchecked, QoS 1).
    """

    name = models.CharField(max_length=255, verbose_name=_("Name"))
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    country = CountryField(
        max_length=2,
        verbose_name=_("Country"),
        help_text=_("Primary country of the authority."),
    )
    sender_values = ArrayField(
        models.CharField(max_length=255),
        default=list,
        verbose_name=_("CAP sender values"),
        help_text=_("Accepted <sender> values. Alerts whose sender does not match are quarantined."),
    )
    contact_email = models.EmailField(blank=True, verbose_name=_("Contact email"))
    active = models.BooleanField(default=True)

    # XMLDSIG verification
    SIGNATURE_POLICIES = (
        ("require", _("Require valid signature")),
        ("verify_if_present", _("Verify when present")),
        ("ignore", _("Ignore signatures")),
    )
    signature_policy = models.CharField(max_length=20, choices=SIGNATURE_POLICIES, default="verify_if_present")
    certificate_pem = models.TextField(blank=True, verbose_name=_("X.509 certificate (PEM)"))

    # MQTT (primary transport)
    mqtt_username = models.CharField(max_length=100, blank=True, editable=False)
    mqtt_password_hash = models.CharField(
        max_length=255, blank=True, editable=False, help_text=_("mosquitto_passwd-compatible hash")
    )
    mqtt_topic = models.CharField(max_length=255, blank=True, editable=False)

    # Fallback transports
    webhook_token = models.CharField(max_length=64, blank=True, editable=False)
    # --- Feed (REQUIRED — the CAP-standard baseline every authority must provide) ---
    # The feed is not merely a fallback: it is polled continuously as a
    # reconciliation sweep. When MQTT/webhook are healthy it runs at the slow
    # (reconcile) interval; when push transports go quiet it tightens to the
    # fast interval. Alerts that arrive ONLY via poll expose broken push
    # transports on the health dashboard (see ingestion.DeliveryReceipt).
    feed_url = models.URLField(
        verbose_name=_("CAP feed URL (RSS/ATOM)"), help_text=_("Required. e.g. https://<composer>/api/cap/rss.xml")
    )
    feed_type_detected = models.CharField(
        max_length=5, blank=True, editable=False,
        help_text=_("RSS/ATOM, sniffed from the feed during the first successful poll (display only)"),
    )
    feed_poll_interval_minutes = models.PositiveIntegerField(
        default=5,
        verbose_name=_("Fast poll interval (min)"),
        help_text=_("Used when no push transport is configured or push has gone quiet"),
    )
    feed_reconcile_interval_minutes = models.PositiveIntegerField(
        default=30,
        verbose_name=_("Reconcile poll interval (min)"),
        help_text=_("Slow sweep used while MQTT/webhook are healthy"),
    )
    # Conditional-GET state
    feed_etag = models.CharField(max_length=255, blank=True, editable=False)
    feed_last_modified = models.CharField(max_length=100, blank=True, editable=False)
    feed_last_polled = models.DateTimeField(null=True, blank=True, editable=False)

    # WMO Registry picker linkage (issue #28) — stamped when an authority is
    # created/linked from the WMO Register of Alerting Authorities. Drives
    # NEEDS UPDATE detection when the registry's feed URL changes. Blank for
    # authorities added by hand, so uniqueness only applies among non-empty
    # values (see Meta.constraints).
    wmo_guid = models.CharField(max_length=255, blank=True, editable=False, verbose_name=_("WMO registry GUID"))
    wmo_feed_url = models.URLField(blank=True, editable=False, verbose_name=_("WMO registry feed URL (captured)"))

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    panels = [
        MultiFieldPanel(
            [
                FieldPanel("name"),
                FieldPanel("country"),
                FieldPanel("sender_values"),
                FieldPanel("contact_email"),
                FieldPanel("active"),
            ],
            heading=_("Authority"),
        ),
        MultiFieldPanel(
            [
                FieldPanel("feed_url"),
                FieldPanel("feed_poll_interval_minutes"),
                FieldPanel("feed_reconcile_interval_minutes"),
            ],
            heading=_("CAP feed (required)"),
        ),
        MultiFieldPanel(
            [FieldPanel("signature_policy"), FieldPanel("certificate_pem")],
            heading=_("Signature verification"),
        ),
    ]

    class Meta:
        verbose_name = _("Source Authority")
        verbose_name_plural = _("Source Authorities")
        ordering = ["country", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["wmo_guid"], condition=~Q(wmo_guid=""), name="unique_non_empty_wmo_guid"
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.country.code})"

    def clean(self):
        # Local-only validation: no network I/O, so saving cannot hang or fail on
        # a slow/unreachable feed. Feed type is sniffed later, during polling.
        if not self.sender_values:
            raise ValidationError({"sender_values": _("At least one CAP sender value is required.")})
        if not self.feed_url:
            raise ValidationError({"feed_url": _("A CAP RSS/ATOM feed URL is required for every authority.")})

    @property
    def has_mqtt_credentials(self) -> bool:
        return bool(self.mqtt_username)

    @property
    def has_push_transport(self) -> bool:
        """MQTT credentials issued, or a webhook token in use. Determines whether
        the feed poller runs at the reconcile interval or the fast interval."""
        return bool(self.mqtt_username)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:100]
        if not self.mqtt_topic:
            self.mqtt_topic = f"cap/in/{self.country.code.lower()}/{self.slug}"
        if not self.webhook_token:
            self.webhook_token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    def issue_mqtt_credentials(self) -> str:
        """Generate MQTT credentials. Returns the plaintext password ONCE —
        only the hash is stored. Broker auth syncs automatically on save."""
        from .mosquitto import hash_password

        self.mqtt_username = f"{self.country.code.lower()}-{self.slug}"[:100]
        password = secrets.token_urlsafe(24)
        self.mqtt_password_hash = hash_password(password)
        self.save(update_fields=["mqtt_username", "mqtt_password_hash"])
        return password
