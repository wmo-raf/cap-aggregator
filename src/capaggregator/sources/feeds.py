"""Feed helpers: type autodiscovery + entry iteration for CAP RSS/ATOM feeds."""

import logging

import requests
from lxml import etree

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15
USER_AGENT = "cap-aggregator/0.1 (+feed-poller)"

ATOM_NS = "http://www.w3.org/2005/Atom"
CAP_MIME_TYPES = ("application/cap+xml", "application/xml", "text/xml")


def autodiscover_feed_type(url: str) -> str | None:
    """Fetch the URL and sniff the root element: <rss> → 'rss', <feed> → 'atom'.
    Returns None if unreachable or not a recognizable feed."""
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        root = etree.fromstring(resp.content)
    except Exception as ex:
        logger.warning("Feed autodiscovery failed for %s: %s", url, ex)
        return None

    tag = etree.QName(root).localname.lower()
    if tag == "rss":
        return "rss"
    if tag == "feed" and etree.QName(root).namespace == ATOM_NS:
        return "atom"
    logger.warning("Feed autodiscovery: unrecognized root <%s> at %s", tag, url)
    return None


def fetch_feed(authority) -> tuple[list[dict], bool]:
    """Conditional GET of the authority's feed. Returns (entries, changed).
    entries = [{'id': ..., 'cap_url': ...}]; changed=False on HTTP 304."""
    import feedparser

    headers = {"User-Agent": USER_AGENT}
    if authority.feed_etag:
        headers["If-None-Match"] = authority.feed_etag
    if authority.feed_last_modified:
        headers["If-Modified-Since"] = authority.feed_last_modified

    resp = requests.get(authority.feed_url, timeout=REQUEST_TIMEOUT, headers=headers)
    if resp.status_code == 304:
        return [], False
    resp.raise_for_status()

    authority.feed_etag = resp.headers.get("ETag", "")
    authority.feed_last_modified = resp.headers.get("Last-Modified", "")

    parsed = feedparser.parse(resp.content)
    entries = []
    for entry in parsed.entries:
        entries.append({
            "id": entry.get("id") or entry.get("guid") or entry.get("link", ""),
            "cap_url": _cap_link(entry),
        })
    return entries, True


def _cap_link(entry) -> str | None:
    """Pick the link most likely to serve the CAP XML for a feed entry.
    Prefers explicit CAP mime types, then any enclosure/alternate, then the entry link."""
    links = entry.get("links", [])
    for mime in CAP_MIME_TYPES:
        for link in links:
            if link.get("type") == mime and link.get("href"):
                return link["href"]
    for link in links:
        if link.get("href"):
            return link["href"]
    return entry.get("link")


def fetch_cap_xml(url: str) -> str:
    resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    return resp.text
