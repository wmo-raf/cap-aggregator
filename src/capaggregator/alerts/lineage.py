"""Lineage resolver — CAP Alert → Update → Cancel chains (docs/design.md §4).

Chains are keyed by the CAP identity triple (sender, identifier, sent) carried
in <references>. Handles out-of-order arrival via DanglingReference rows and
merges chains when a late-arriving message connects two of them.
"""

import logging
from datetime import datetime, timedelta

from django.db import transaction

logger = logging.getLogger(__name__)

# CAP <expires> is optional (validators only warn). A NULL expiry must never
# reach the read model: the tile SQL would render the alert forever while the
# homepage's `expires > now` queries silently drop it. Alerts without an
# explicit expiry get this default active window from their effective time.
DEFAULT_ACTIVE_WINDOW = timedelta(hours=24)


@transaction.atomic
def resolve(alert):
    """Attach `alert` to its chain (creating/merging as needed) and refresh
    the chain's ResolvedAlert. Returns the EventChain."""
    from .models import Alert, DanglingReference, EventChain

    chains = set()

    # 1. Walk references → find existing chains
    for ref in alert.references:
        try:
            ref_sent = datetime.fromisoformat(ref["sent"])
        except (KeyError, ValueError):
            continue
        referenced = Alert.objects.filter(
            sender=ref["sender"], identifier=ref["identifier"], sent=ref_sent
        ).select_related("chain").first()
        if referenced and referenced.chain_id:
            chains.add(referenced.chain)
        else:
            DanglingReference.objects.create(
                alert=alert, ref_sender=ref.get("sender", ""),
                ref_identifier=ref.get("identifier", ""), ref_sent=ref_sent,
            )

    # 2. Did any earlier message dangle a reference to *this* alert? (out-of-order)
    dangling = DanglingReference.objects.filter(
        ref_sender=alert.sender, ref_identifier=alert.identifier,
        ref_sent=alert.sent, resolved=False,
    ).select_related("alert__chain")
    for d in dangling:
        if d.alert.chain_id:
            chains.add(d.alert.chain)
        d.resolved = True
        d.save(update_fields=["resolved"])

    # 3. Create / pick / merge chains
    if not chains:
        chain = EventChain.objects.create(
            authority=alert.authority, first_alert=alert, latest_alert=alert,
            incomplete_chain=bool(alert.references) and alert.msg_type != "Alert",
        )
    else:
        chain, *others = sorted(chains, key=lambda c: c.pk)
        for other in others:  # merge
            other.alerts.update(chain=chain)
            if hasattr(other, "resolved"):
                other.resolved.delete()
            other.delete()
            logger.info("Merged chain %s into %s", other.pk, chain.pk)

    alert.chain = chain
    alert.save(update_fields=["chain"])

    # 4. Update chain head/flags
    latest = chain.alerts.order_by("-sent").first()
    first = chain.alerts.order_by("sent").first()
    chain.latest_alert = latest
    chain.first_alert = first
    chain.is_cancelled = chain.alerts.filter(msg_type="Cancel").exists()
    chain.save()

    _refresh_resolved(chain)
    return chain


def _refresh_resolved(chain):
    """Rebuild the denormalized ResolvedAlert row for a chain."""
    from django.contrib.gis.geos import GEOSGeometry, MultiPolygon

    from .models import ResolvedAlert

    latest = chain.latest_alert
    # Content comes from the latest non-Cancel message; a Cancel keeps the last
    # content but flags the chain cancelled.
    content_alert = latest
    if latest.msg_type == "Cancel":
        content_alert = chain.alerts.exclude(msg_type="Cancel").order_by("-sent").first() or latest

    info = content_alert.infos.order_by("language").first()
    if info is None:
        logger.warning("Chain %s latest alert has no info block", chain.pk)
        return

    # Union all area geometries of the content alert
    geoms = [a.geom for i in content_alert.infos.all() for a in i.areas.all() if a.geom]
    geom = None
    if geoms:
        merged = geoms[0]
        for g in geoms[1:]:
            merged = merged.union(g)
        if merged.geom_type == "Polygon":
            merged = MultiPolygon(GEOSGeometry(merged.wkt), srid=4326)
        geom = merged

    effective = info.effective or content_alert.sent
    defaults = {
        "authority": chain.authority,
        "latest_alert": latest,
        "msg_type": latest.msg_type,
        "status": latest.status,
        "event": info.event,
        "categories": info.categories,
        "urgency": info.urgency,
        "severity": info.severity,
        "certainty": info.certainty,
        "languages": list(content_alert.infos.values_list("language", flat=True)),
        "headline": info.headline,
        "onset": info.onset,
        "effective": effective,
        "expires": info.expires or effective + DEFAULT_ACTIVE_WINDOW,
        "is_cancelled": chain.is_cancelled,
        "countries": _attribute_countries(chain.authority, geom),
        "geom": geom,
        "geom_z8": _simplify(geom, 0.01),
        "geom_z5": _simplify(geom, 0.05),
        "centroid": geom.centroid if geom else None,
    }
    ResolvedAlert.objects.update_or_create(chain=chain, defaults=defaults)


def _simplify(geom, tolerance):
    from django.contrib.gis.geos import MultiPolygon

    if geom is None:
        return None
    simplified = geom.simplify(tolerance, preserve_topology=True)
    if simplified.geom_type == "Polygon":
        simplified = MultiPolygon(simplified, srid=4326)
    return simplified


def _attribute_countries(authority, geom) -> list[str]:
    """Issuing authority's country + every admin-0 boundary the geometry intersects.
    TODO: intersect with adminboundarymanager admin-0 once boundaries are loaded."""
    countries = [authority.country.code.lower()]
    return countries
