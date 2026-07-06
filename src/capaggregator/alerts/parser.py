"""Parse a validated CAP XML message into Alert/AlertInfo/AlertArea rows.

Geometry handling:
- <polygon>: "lat,lon lat,lon ..." (CAP order!) → shapely Polygon (lon/lat), ST_MakeValid fixups
- <circle>: "lat,lon radiusKm" → geodesic buffer via pyproj azimuthal projection
- <geocode>-only areas: resolved via the geocode registry (versioned at alert.sent)
"""

import logging
from datetime import datetime

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from lxml import etree
from shapely.geometry import Polygon
from shapely.ops import transform, unary_union

from capaggregator.ingestion.validators import CAP

logger = logging.getLogger(__name__)


def parse_identity(xml: str) -> dict | None:
    """Cheaply extract the CAP identity triple (sender, identifier, sent) for
    cross-transport dedup — before full validation/parsing. Returns None if the
    XML is unparseable or the triple is incomplete (validation will handle it)."""
    try:
        tree = etree.fromstring(xml.encode())
    except etree.XMLSyntaxError:
        return None
    sender = _text(tree, "sender")
    identifier = _text(tree, "identifier")
    sent = _dt(_text(tree, "sent"))
    if not (sender and identifier and sent):
        return None
    return {"sender": sender, "identifier": identifier, "sent": sent}


def parse_and_store(raw, warnings: list | None = None):
    """Create the Alert graph from a RawMessage. Returns the Alert."""
    from .models import Alert, AlertArea, AlertInfo

    tree = etree.fromstring(raw.xml.encode())

    alert = Alert.objects.create(
        authority=raw.authority,
        raw_message=raw,
        identifier=_text(tree, "identifier"),
        sender=_text(tree, "sender"),
        sent=_dt(_text(tree, "sent")),
        msg_type=_text(tree, "msgType"),
        status=_text(tree, "status"),
        scope=_text(tree, "scope"),
        references=_parse_references(_text(tree, "references")),
        note=_text(tree, "note"),
        validation_warnings=warnings or [],
    )

    for info_el in tree.findall(f"{CAP}info"):
        info = AlertInfo.objects.create(
            alert=alert,
            language=_text(info_el, "language") or "en-US",
            categories=[e.text for e in info_el.findall(f"{CAP}category") if e.text],
            event=_text(info_el, "event"),
            response_types=[e.text for e in info_el.findall(f"{CAP}responseType") if e.text],
            urgency=_text(info_el, "urgency"),
            severity=_text(info_el, "severity"),
            certainty=_text(info_el, "certainty"),
            audience=_text(info_el, "audience"),
            onset=_dt(_text(info_el, "onset")),
            effective=_dt(_text(info_el, "effective")),
            expires=_dt(_text(info_el, "expires")),
            sender_name=_text(info_el, "senderName"),
            headline=_text(info_el, "headline"),
            description=_text(info_el, "description"),
            instruction=_text(info_el, "instruction"),
            web=_text(info_el, "web"),
            contact=_text(info_el, "contact"),
            parameters=_kv_pairs(info_el, "parameter"),
            event_codes=_kv_pairs(info_el, "eventCode"),
        )

        for area_el in info_el.findall(f"{CAP}area"):
            geom, is_circle, is_geocode = _build_area_geometry(area_el, alert.sent)
            AlertArea.objects.create(
                info=info,
                area_desc=_text(area_el, "areaDesc"),
                geom=geom,
                is_circle_derived=is_circle,
                is_geocode_derived=is_geocode,
                geocodes=_kv_pairs(area_el, "geocode", multi=True),
                altitude=_float(_text(area_el, "altitude")),
                ceiling=_float(_text(area_el, "ceiling")),
            )

    return alert


# --- helpers ---------------------------------------------------------------


def _text(el, tag) -> str:
    return (el.findtext(f"{CAP}{tag}") or "").strip()


def _dt(value: str) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _float(value: str) -> float | None:
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _kv_pairs(el, tag, multi=False) -> dict:
    """<parameter>/<eventCode>/<geocode> valueName/value pairs → dict."""
    out: dict = {}
    for pair in el.findall(f"{CAP}{tag}"):
        name = (pair.findtext(f"{CAP}valueName") or "").strip()
        value = (pair.findtext(f"{CAP}value") or "").strip()
        if not name:
            continue
        if multi:
            out.setdefault(name, []).append(value)
        else:
            out[name] = value
    return out


def _parse_references(references: str) -> list[dict]:
    """'sender,identifier,sent sender,identifier,sent' → list of dicts."""
    out = []
    for triple in references.split():
        parts = triple.split(",")
        if len(parts) == 3:
            out.append({"sender": parts[0], "identifier": parts[1], "sent": parts[2]})
    return out


def _build_area_geometry(area_el, sent) -> tuple[MultiPolygon | None, bool, bool]:
    """Returns (geom, is_circle_derived, is_geocode_derived)."""
    shapes = []
    is_circle = False
    is_geocode = False

    for polygon_el in area_el.findall(f"{CAP}polygon"):
        shape = _polygon_from_cap((polygon_el.text or "").strip())
        if shape is not None:
            shapes.append(shape)

    for circle_el in area_el.findall(f"{CAP}circle"):
        shape = _circle_from_cap((circle_el.text or "").strip())
        if shape is not None:
            shapes.append(shape)
            is_circle = True

    if not shapes:
        geom = _geometry_from_geocodes(_kv_pairs(area_el, "geocode", multi=True), sent)
        if geom is not None:
            return geom, False, True
        return None, False, False

    merged = unary_union(shapes)
    geos = GEOSGeometry(merged.wkt, srid=4326)
    if geos.geom_type == "Polygon":
        geos = MultiPolygon(geos, srid=4326)
    if not geos.valid:
        geos = geos.buffer(0)
        if geos.geom_type == "Polygon":
            geos = MultiPolygon(geos, srid=4326)
    return geos, is_circle, is_geocode


def _polygon_from_cap(text: str) -> Polygon | None:
    """CAP polygon: whitespace-separated 'lat,lon' pairs (note the order)."""
    if not text:
        return None
    try:
        coords = [(float(lon), float(lat)) for lat, lon in
                  (pair.split(",") for pair in text.split())]
    except ValueError:
        logger.warning("Unparseable polygon: %.80s", text)
        return None
    if len(coords) < 4:
        return None
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return Polygon(coords)


def _circle_from_cap(text: str) -> Polygon | None:
    """CAP circle: 'lat,lon radiusKm' → geodesic buffer (azimuthal equidistant)."""
    import pyproj

    try:
        center, radius_km = text.split()
        lat, lon = (float(v) for v in center.split(","))
        radius_m = float(radius_km) * 1000.0
    except ValueError:
        logger.warning("Unparseable circle: %.80s", text)
        return None

    aeqd = pyproj.CRS(proj="aeqd", lat_0=lat, lon_0=lon, datum="WGS84")
    wgs84 = pyproj.CRS("EPSG:4326")
    to_aeqd = pyproj.Transformer.from_crs(wgs84, aeqd, always_xy=True).transform
    to_wgs84 = pyproj.Transformer.from_crs(aeqd, wgs84, always_xy=True).transform

    from shapely.geometry import Point

    buffered = transform(to_aeqd, Point(lon, lat)).buffer(radius_m, quad_segs=32)
    return transform(to_wgs84, buffered)


def _geometry_from_geocodes(geocodes: dict, sent) -> MultiPolygon | None:
    """Resolve geocode-only areas via the versioned geocode registry."""
    from capaggregator.geocodes.resolver import resolve_geocodes

    return resolve_geocodes(geocodes, at=sent)
