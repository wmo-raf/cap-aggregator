from django.core.cache import cache
from django.db import models
from django.utils import timezone
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.models import Page

STATS_CACHE_KEY = "capagg-home-stats"
STATS_CACHE_TTL = 60  # seconds — counts don't need to be per-request fresh
LATEST_ALERTS_LIMIT = 6


class HomePage(Page):
    """The public landing page (supersedes the design doc's map-as-home idea):
    hero with CTA to the explorer, cached stats strip, latest alerts."""

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
        from capaggregator.sources.models import SourceAuthority

        context = super().get_context(request, *args, **kwargs)

        def compute_stats():
            now = timezone.now()
            active = ResolvedAlert.objects.filter(is_cancelled=False, effective__lte=now, expires__gt=now)
            return {
                "active_alerts": active.count(),
                "authorities": SourceAuthority.objects.filter(active=True).count(),
                "countries": SourceAuthority.objects.filter(active=True).values("country").distinct().count(),
            }

        context["stats"] = cache.get_or_set(STATS_CACHE_KEY, compute_stats, STATS_CACHE_TTL)
        now = timezone.now()
        context["latest_alerts"] = (
            ResolvedAlert.objects.filter(is_cancelled=False, effective__lte=now, expires__gt=now)
            .select_related("authority")
            .order_by("-effective")[:LATEST_ALERTS_LIMIT]
        )
        return context
