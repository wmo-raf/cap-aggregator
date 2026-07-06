"""API views — search, histogram, SSE live stream. Skeletons to build on."""

import json

from django.http import JsonResponse, StreamingHttpResponse
from rest_framework.generics import ListAPIView

from capaggregator.alerts.models import ResolvedAlert

from .serializers import ResolvedAlertSerializer


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

        # Point-in-time (default: only currently active) or interval
        if t := params.get("t"):
            qs = qs.filter(effective__lte=t, expires__gt=t)
        elif params.get("active", "true").lower() == "true":
            from django.utils import timezone

            now = timezone.now()
            qs = qs.filter(effective__lte=now, expires__gt=now)

        if bbox := params.get("bbox"):
            from django.contrib.gis.geos import Polygon

            qs = qs.filter(geom__intersects=Polygon.from_bbox([float(v) for v in bbox.split(",")]))

        # TODO: full-text q over AlertInfo.search_vector; language filter; resolved=false raw mode
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
