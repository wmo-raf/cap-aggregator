import json

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from capaggregator.alerts.models import Alert, EventChain, ResolvedAlert


def alert_detail(request, chain_id):
    """Chain-canonical alert page: one stable URL per event chain, rendering the
    resolved current state (survives Alert → Update → Cancel supersession)."""
    chain = get_object_or_404(
        EventChain.objects.select_related("authority", "latest_alert", "resolved"),
        pk=chain_id,
    )
    infos = chain.latest_alert.infos.prefetch_related("areas")
    resolved = chain.resolved
    is_expired = bool(
        not chain.is_cancelled and resolved.expires and resolved.expires < timezone.now()
    )
    return render(
        request,
        "capagg_alerts/alert_detail.html",
        {
            "chain": chain,
            "resolved": resolved,
            "alert": chain.latest_alert,
            "infos": infos,
            "is_expired": is_expired,
            # GeoJSON for the progressive-enhancement area map (json_script)
            "area_geojson": json.loads(resolved.geom.geojson) if resolved.geom else None,
            "timeline": chain.alerts.order_by("sent"),
            "related": (
                ResolvedAlert.objects.filter(authority=chain.authority)
                .exclude(chain=chain)
                .select_related("chain")
                .order_by("-effective")[:5]
            ),
        },
    )


def alert_version(request, chain_id, alert_id):
    """A single immutable message in the chain, rendered — with a superseded
    banner unless it is the latest."""
    alert = get_object_or_404(
        Alert.objects.select_related("chain__authority"), pk=alert_id, chain_id=chain_id
    )
    chain = alert.chain
    return render(
        request,
        "capagg_alerts/alert_version.html",
        {
            "chain": chain,
            "alert": alert,
            "infos": alert.infos.all(),
            "is_current": chain.latest_alert_id == alert.pk,
        },
    )


def alert_xml(request, chain_id):
    """The original (possibly signed) CAP XML of the chain's latest message —
    the verifiable source artifact, served unmodified."""
    chain = get_object_or_404(
        EventChain.objects.select_related("latest_alert__raw_message"), pk=chain_id
    )
    return HttpResponse(chain.latest_alert.raw_message.xml, content_type="application/xml")
