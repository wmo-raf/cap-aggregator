import json

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from capaggregator.alerts.models import EventChain


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
        },
    )


def alert_xml(request, chain_id):
    """The original (possibly signed) CAP XML of the chain's latest message —
    the verifiable source artifact, served unmodified."""
    chain = get_object_or_404(
        EventChain.objects.select_related("latest_alert__raw_message"), pk=chain_id
    )
    return HttpResponse(chain.latest_alert.raw_message.xml, content_type="application/xml")
