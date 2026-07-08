"""WMO Register of Alerting Authorities picker (issue #28): fetch + cache the
live register, parse it, and derive an import status per entry against the
existing SourceAuthority table. Read-only in this slice — Apply/create lands in
a later issue.
"""

import logging
from dataclasses import dataclass
from functools import lru_cache

import requests
from django.core.cache import cache
from lxml import etree

from .feeds import REQUEST_TIMEOUT, USER_AGENT

logger = logging.getLogger(__name__)

WMO_REGISTRY_URL = "https://alertingauthority.wmo.int/rss.xml"
WMO_REGISTRY_CACHE_KEY = "capagg:sources:wmo_registry"
WMO_REGISTRY_CACHE_TTL = 3600

RAA_NS = "http://www.oid-info.com/get/2.49.0"
ISO_NS = "http://www.itu.int/tML/tML-ISO-3166"
XML_NS = "http://www.w3.org/XML/1998/namespace"
_NSMAP = {"raa": RAA_NS, "iso": ISO_NS}


def fetch_wmo_registry(refresh: bool = False) -> tuple[bytes | None, str | None]:
    """Fetch the WMO Register of Alerting Authorities, caching the raw response
    for WMO_REGISTRY_CACHE_TTL seconds. Returns (content, error): on success
    content is the raw feed bytes and error is None; on failure content is None
    and error is a message the picker can render. refresh=True bypasses and
    repopulates the cache (the picker's Refresh button)."""
    if not refresh:
        cached = cache.get(WMO_REGISTRY_CACHE_KEY)
        if cached is not None:
            return cached, None

    try:
        response = requests.get(WMO_REGISTRY_URL, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
    except requests.RequestException:
        logger.warning("WMO registry fetch failed", exc_info=True)
        return None, "Could not reach the WMO Register of Alerting Authorities. Try again later."

    content = response.content
    cache.set(WMO_REGISTRY_CACHE_KEY, content, WMO_REGISTRY_CACHE_TTL)
    return content, None


@dataclass
class RegistryEntry:
    """One parsed <item> from the WMO register feed."""

    guid: str
    name: str
    country: str | None  # ISO alpha-2, or None if the alpha-3 code is unmappable
    feed_url: str | None  # English raa:capAlertFeed, else the first listed, else None
    contact_email: str
    abbrev: str


def parse_wmo_registry(content: bytes) -> list[RegistryEntry]:
    """Pure parse of the WMO register RSS feed. lxml (not feedparser) — the feed's
    repeated, xml:lang-tagged raa:capAlertFeed and iso:countrycode elements are not
    reliably exposed by feedparser."""
    root = etree.fromstring(content)
    return [_parse_item(item) for item in root.findall(".//item")]


def _parse_item(item) -> RegistryEntry:
    title = (item.findtext("title") or "").strip()
    name = title.split(": ", 1)[1] if ": " in title else title
    alpha3 = (item.findtext("iso:countrycode", namespaces=_NSMAP) or "").strip()

    return RegistryEntry(
        guid=(item.findtext("guid") or "").strip(),
        name=name,
        country=_alpha3_to_alpha2().get(alpha3.upper()),
        feed_url=_select_feed_url(item),
        contact_email=(item.findtext("author") or "").strip(),
        abbrev=(item.findtext("raa:authorityAbbrev", namespaces=_NSMAP) or "").strip(),
    )


@lru_cache(maxsize=1)
def _alpha3_to_alpha2() -> dict[str, str]:
    """django-countries doesn't ship an alpha3->alpha2 map; build one from the
    alpha-2 registry it does provide."""
    from django_countries import countries
    from django_countries.fields import Country

    return {Country(code).alpha3: code for code, _name in countries}


def _select_feed_url(item) -> str | None:
    feeds = item.findall("raa:capAlertFeed", namespaces=_NSMAP)
    if not feeds:
        return None
    for feed in feeds:
        if feed.get(f"{{{XML_NS}}}lang") == "en":
            return (feed.text or "").strip()
    return (feeds[0].text or "").strip()


# --- Status derivation (DB read) -------------------------------------------

STATUS_NEW = "NEW"
STATUS_ALREADY_EXISTS = "ALREADY_EXISTS"
STATUS_UP_TO_DATE = "UP_TO_DATE"
STATUS_NEEDS_UPDATE = "NEEDS_UPDATE"
STATUS_NO_FEED = "NO_FEED"
STATUS_INVALID_COUNTRY = "INVALID_COUNTRY"

STATUS_LABELS = {
    STATUS_NEW: "NEW",
    STATUS_ALREADY_EXISTS: "ALREADY EXISTS",
    STATUS_UP_TO_DATE: "UP TO DATE",
    STATUS_NEEDS_UPDATE: "NEEDS UPDATE",
    STATUS_NO_FEED: "NO FEED",
    STATUS_INVALID_COUNTRY: "INVALID COUNTRY",
}


@dataclass
class RegistryRow:
    """One picker row: a parsed entry plus its derived import status."""

    entry: RegistryEntry
    status: str
    selectable: bool
    authority_id: int | None = None

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.status]


def derive_registry_view(entries: list[RegistryEntry]) -> list[RegistryRow]:
    """Annotate each parsed entry with an import status by matching it against
    existing SourceAuthority rows — by wmo_guid first, then by feed_url."""
    return [_derive_row(entry) for entry in entries]


def _derive_row(entry: RegistryEntry) -> RegistryRow:
    if not entry.feed_url:
        return RegistryRow(entry=entry, status=STATUS_NO_FEED, selectable=False)
    if not entry.country:
        return RegistryRow(entry=entry, status=STATUS_INVALID_COUNTRY, selectable=False)

    match = _find_matching_authority(entry)
    if match is None:
        return RegistryRow(entry=entry, status=STATUS_NEW, selectable=True)
    if not match.wmo_guid:
        return RegistryRow(entry=entry, status=STATUS_ALREADY_EXISTS, selectable=True, authority_id=match.id)
    if entry.feed_url == match.wmo_feed_url:
        return RegistryRow(entry=entry, status=STATUS_UP_TO_DATE, selectable=False, authority_id=match.id)
    return RegistryRow(entry=entry, status=STATUS_NEEDS_UPDATE, selectable=True, authority_id=match.id)


def _find_matching_authority(entry: RegistryEntry):
    from .models import SourceAuthority

    if entry.guid:
        match = SourceAuthority.objects.filter(wmo_guid=entry.guid).first()
        if match is not None:
            return match
    return SourceAuthority.objects.filter(feed_url=entry.feed_url).first()
