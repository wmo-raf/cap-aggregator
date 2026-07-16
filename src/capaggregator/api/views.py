"""API views — search, authorities, histogram, SSE live stream."""

from datetime import timedelta

from django.db.models import Case, Count, IntegerField, Q, When
from django.http import JsonResponse, StreamingHttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import ListAPIView

from capaggregator.alerts.models import ResolvedAlert
from capaggregator.sources.models import SourceAuthority

from .serializers import ResolvedAlertSerializer, SourceAuthoritySerializer


class AuthorityListView(ListAPIView):
    """GET /api/authorities/ — active authorities with their current activity.

    Public read model for the explorer's Authorities view: name, slug, country,
    website and the number of currently-active resolved alerts."""

    serializer_class = SourceAuthoritySerializer

    def get_queryset(self):
        now = timezone.now()
        return (
            SourceAuthority.objects.filter(active=True)
            .annotate(
                active_alert_count=Count(
                    "resolved_alerts",
                    filter=Q(
                        resolved_alerts__is_cancelled=False,
                        resolved_alerts__effective__lte=now,
                        resolved_alerts__expires__gt=now,
                    ),
                )
            )
            .order_by("name")
        )


def _parse_bound(value, *, end=False):
    """ISO datetime, or bare date. A bare date used as an upper bound is
    inclusive of that whole day (< next midnight). Checked date-first:
    Django 5's parse_datetime (fromisoformat) also accepts bare dates."""
    if d := parse_date(value):
        dt = timezone.make_aware(timezone.datetime(d.year, d.month, d.day))
        return (dt + timedelta(days=1), True) if end else (dt, False)
    if dt := parse_datetime(value):
        return (timezone.make_aware(dt) if timezone.is_naive(dt) else dt), False
    return None, False


@extend_schema(
    parameters=[
        OpenApiParameter("effective_from", str, description="Range mode: alerts effective on/after this ISO datetime or date."),
        OpenApiParameter("effective_to", str, description="Range mode: alerts effective up to this ISO datetime (or through this date). Range mode includes expired alerts."),
        OpenApiParameter("t", str, description="Point-in-time: alerts active at this instant (default: now when active=true)."),
        OpenApiParameter("upcoming", str, description="'true' returns the active + future union (non-cancelled, expires > now) — e.g. for deriving time-selector options."),
        OpenApiParameter("order", str, description="'severity' ranks worst-first (Extreme→Unknown, newest within); 'country' sorts by issuing authority's country, then authority name, newest within; default is newest-first."),
    ]
)
class AlertSearchView(ListAPIView):
    """GET /api/search/?country=ke&severity=Severe,Extreme&t=...&q=flood&bbox=..."""

    serializer_class = ResolvedAlertSerializer

    def get_queryset(self):
        qs = ResolvedAlert.objects.select_related("authority", "latest_alert")
        params = self.request.query_params

        csv_filters = {
            "severity": "severity__in",
            "urgency": "urgency__in",
            "certainty": "certainty__in",
            "msg_type": "msg_type__in",
            "status": "status__in",
        }
        for param, lookup in csv_filters.items():
            if value := params.get(param):
                qs = qs.filter(**{lookup: value.split(",")})

        if country := params.get("country"):
            qs = qs.filter(countries__overlap=country.lower().split(","))
        if category := params.get("category"):
            qs = qs.filter(categories__overlap=category.split(","))
        if event := params.get("event"):
            qs = qs.filter(event__icontains=event)

        # Time: effective-date range (archive — includes expired), else the
        # active + future union (upcoming), else point-in-time t, else the
        # currently-active default
        effective_from = params.get("effective_from")
        effective_to = params.get("effective_to")
        if params.get("upcoming", "").lower() == "true":
            qs = qs.filter(is_cancelled=False, expires__gt=timezone.now())
        elif effective_from or effective_to:
            if effective_from:
                bound, _ = _parse_bound(effective_from)
                if bound:
                    qs = qs.filter(effective__gte=bound)
            if effective_to:
                bound, exclusive = _parse_bound(effective_to, end=True)
                if bound:
                    qs = qs.filter(**{"effective__lt" if exclusive else "effective__lte": bound})
        elif t := params.get("t"):
            qs = qs.filter(effective__lte=t, expires__gt=t)
        elif params.get("active", "true").lower() == "true":
            now = timezone.now()
            qs = qs.filter(effective__lte=now, expires__gt=now)

        if bbox := params.get("bbox"):
            from django.contrib.gis.geos import Polygon

            qs = qs.filter(geom__intersects=Polygon.from_bbox([float(v) for v in bbox.split(",")]))

        # TODO: full-text q over AlertInfo.search_vector; language filter; resolved=false raw mode
        if params.get("order") == "country":
            # keeps Country > Authority grouped, paginated lists globally contiguous
            return qs.order_by("authority__country", "authority__name", "-effective")
        if params.get("order") == "severity":
            # keeps severity-grouped, paginated lists globally contiguous
            rank = Case(
                When(severity="Extreme", then=0),
                When(severity="Severe", then=1),
                When(severity="Moderate", then=2),
                When(severity="Minor", then=3),
                default=4,
                output_field=IntegerField(),
            )
            return qs.annotate(_severity_rank=rank).order_by("_severity_rank", "-effective")
        return qs.order_by("-effective")


def histogram(request):
    """Alert counts per time bucket. TODO: back with a
    count(*) GROUP BY date_trunc(...) query over the alert_activity table."""
    return JsonResponse({"buckets": [], "detail": "not implemented yet"}, status=501)


def event_stream(request):
    """SSE endpoint for live mode — relays Redis pub/sub 'capagg:alerts'.
    Note: run under ASGI (or a dedicated worker) in production."""
    import redis
    from django.conf import settings

    def stream():
        r = redis.from_url(settings.REDIS_URL)
        pubsub = r.pubsub()
        pubsub.subscribe("capagg:alerts")
        for message in pubsub.listen():
            if message["type"] == "message":
                yield f"data: {message['data'].decode()}\n\n"

    response = StreamingHttpResponse(stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    return response
