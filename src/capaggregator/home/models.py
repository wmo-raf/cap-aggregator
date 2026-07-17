from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import models
from django.utils import timezone
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.models import Page

STATS_CACHE_KEY = "capagg-home-stats"
STATS_CACHE_TTL = 60  # seconds — counts don't need to be per-request fresh
VISIBLE_ALERTS_PER_AUTHORITY = 2

# Worst-first; anything else ranks after Minor
SEVERITY_ORDER = ("Extreme", "Severe", "Moderate", "Minor")

# "Operational" while the newest successful source contact is at most this old
OPERATIONAL_WINDOW = timedelta(minutes=15)


def _severity_rank(severity):
    try:
        return SEVERITY_ORDER.index(severity)
    except ValueError:
        return len(SEVERITY_ORDER)


def _flag_emoji(code):
    if len(code) != 2 or not code.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code.upper())


def _severity_breakdown(counter):
    """Stable Extreme→Minor list for the stat cards (zeros kept, dimmed in CSS)."""
    return [
        {"severity": s, "count": counter.get(s, 0)}
        for s in SEVERITY_ORDER
    ]


class HomePage(Page):
    """The public landing page (supersedes the design doc's map-as-home idea):
    hero with CTA to the explorer, cached current-situation stats, and all
    active alerts grouped per authority."""

    max_count = 1
    template = "capagg_home/home_page.html"

    hero_heading = models.CharField(
        max_length=255,
        default="Emergency alerts from official sources, on one map",
    )
    hero_intro = models.TextField(
        blank=True,
        default=(
            "CAP Aggregator collects Common Alerting Protocol warnings from national "
            "meteorological and hydrological services and serves them as one authoritative, "
            "always-current picture."
        ),
    )
    hero_image = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Optional hero background; a default is used when empty.",
    )

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [FieldPanel("hero_heading"), FieldPanel("hero_intro"), FieldPanel("hero_image")],
            heading="Hero",
        ),
    ]

    def get_context(self, request, *args, **kwargs):
        from capaggregator.alerts.models import ResolvedAlert
        from capaggregator.ingestion.models import SourceEvent
        from capaggregator.sources.models import SourceAuthority

        context = super().get_context(request, *args, **kwargs)
        now = timezone.now()
        # Only status=Actual is a real public warning — Exercise/Test/System/
        # Draft alerts must never appear in the public current situation (the
        # homepage map JS passes the same status filter to the tile function)
        active = ResolvedAlert.objects.filter(
            status="Actual", is_cancelled=False, effective__lte=now, expires__gt=now,
        )

        def compute_stats():
            alert_counts = {}
            country_worst = {}
            total = 0
            for severity, countries in active.values_list("severity", "countries"):
                total += 1
                alert_counts[severity] = alert_counts.get(severity, 0) + 1
                for country in countries:
                    code = country.upper()
                    if code not in country_worst or _severity_rank(severity) < _severity_rank(country_worst[code]):
                        country_worst[code] = severity
            country_counts = {}
            for severity in country_worst.values():
                country_counts[severity] = country_counts.get(severity, 0) + 1

            last_event = (
                SourceEvent.objects.filter(ok=True).order_by("-occurred_at").values_list("occurred_at", flat=True).first()
            )
            if last_event is None:
                status = "unknown"
            elif timezone.now() - last_event <= OPERATIONAL_WINDOW:
                status = "operational"
            else:
                status = "degraded"

            return {
                "active_alerts": total,
                "alert_severity_counts": _severity_breakdown(alert_counts),
                "countries_with_alerts": len(country_worst),
                "countries_covered": (
                    SourceAuthority.objects.filter(active=True).values("country").distinct().count()
                ),
                "country_severity_counts": _severity_breakdown(country_counts),
                "last_check": last_event,
                "status": status,
            }

        context["stats"] = cache.get_or_set(STATS_CACHE_KEY, compute_stats, STATS_CACHE_TTL)

        # Active + upcoming alerts grouped per authority, worst severity first.
        # Upcoming items ship hidden (data-upcoming) with data-effective/expires
        # attributes; the homepage map JS toggles them for the selected time.
        listed = ResolvedAlert.objects.filter(status="Actual", is_cancelled=False, expires__gt=now)
        groups = {}
        for alert in listed.select_related("authority").order_by("-effective"):
            group = groups.get(alert.authority_id)
            if group is None:
                code = str(alert.authority.country)
                group = groups[alert.authority_id] = {
                    "authority": alert.authority,
                    "country_code": code,
                    "country_name": alert.authority.country.name,
                    "flag": _flag_emoji(code),
                    "alerts": [],
                    "worst_rank": _severity_rank(alert.severity),
                }
            upcoming = alert.effective is not None and alert.effective > now
            group["alerts"].append({"alert": alert, "upcoming": upcoming, "extra": False})
            group["worst_rank"] = min(group["worst_rank"], _severity_rank(alert.severity))
        for group in groups.values():
            current = [entry for entry in group["alerts"] if not entry["upcoming"]]
            for position, entry in enumerate(current):
                entry["extra"] = position >= VISIBLE_ALERTS_PER_AUTHORITY
            group["active_count"] = len(current)
            group["extra_count"] = max(0, len(current) - VISIBLE_ALERTS_PER_AUTHORITY)
        context["alert_groups"] = sorted(
            groups.values(), key=lambda g: (g["worst_rank"], g["country_name"], g["authority"].name)
        )
        context["visible_per_authority"] = VISIBLE_ALERTS_PER_AUTHORITY
        context["severity_levels"] = SEVERITY_ORDER
        # json_script the homepage map JS boots from (frontend/src/lib/config.ts)
        context["capagg_config"] = {"tilesBase": settings.CAPAGG_TILES_BASE}
        return context
