"""Feed helpers: entry iteration + type detection for CAP RSS/ATOM feeds."""

import logging

import requests

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15
USER_AGENT = "cap-aggregator/0.1 (+feed-poller)"

CAP_MIME_TYPES = ("application/cap+xml", "application/xml", "text/xml")


def _detected_feed_type(parsed) -> str:
    """Map feedparser's version ('rss20', 'atom10', …) to 'rss'/'atom' for display."""
    version = (getattr(parsed, "version", "") or "").lower()
    if version.startswith("atom"):
        return "atom"
    if version.startswith("rss") or version.startswith("rdf"):
        return "rss"
    return ""


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
    authority.feed_type_detected = _detected_feed_type(parsed)
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
