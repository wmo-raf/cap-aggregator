import logging

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.db.models import Q

logger = logging.getLogger(__name__)


def resolve_geocodes(geocodes: dict, at=None) -> MultiPolygon | None:
    """Resolve {scheme: [values]} to a merged geometry, using the version
    valid at `at` (alert sent time). Returns None if nothing resolves —
    the caller records this as a validation warning/error."""
    from .models import GeocodeValue

    geoms = []
    for scheme_name, values in geocodes.items():
        qs = GeocodeValue.objects.filter(scheme__name=scheme_name, value__in=values)
        if at is not None:
            qs = qs.filter(
                Q(valid_from__isnull=True) | Q(valid_from__lte=at),
                Q(valid_to__isnull=True) | Q(valid_to__gte=at),
            )
        found = list(qs)
        missing = set(values) - {g.value for g in found}
        if missing:
            logger.info("Unresolved geocodes %s:%s", scheme_name, sorted(missing))
        geoms += [g.geom for g in found]

    if not geoms:
        return None

    merged = geoms[0]
    for g in geoms[1:]:
        merged = merged.union(g)
    if merged.geom_type == "Polygon":
        merged = MultiPolygon(GEOSGeometry(merged.wkt), srid=4326)
    return merged
