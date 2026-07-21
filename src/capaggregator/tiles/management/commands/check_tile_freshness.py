"""Management command: check_tile_freshness

Integration check against a *running* Martin: does an unchanged tile URL still
reflect the database after the database changes?

This is the seam the unit tests cannot reach. They assert the URL the client
builds; nothing in `manage.py test` can assert what the tile server returns,
because Django's test database is invisible to Martin — Martin holds its own
connection to the application database. So this check talks to the real database
through the ORM and to Martin over HTTP, which means it must run as a command
rather than a test case.

It exists because of a production bug: Martin's in-memory tile cache is an LRU
with *no TTL*, so a tile URL that never changed (live mode used to omit `t`) was
served from one render until the process restarted — alerts that had expired
days earlier stayed on the map while the server-rendered list was correct.

The probe alert is status=Test and carries a unique event marker, and the tile
is requested filtered to both, so it is invisible to every public surface (they
all pin status=Actual) and isolated from real data. It is deleted again in a
finally.

Usage:
    capagg check_tile_freshness
    capagg check_tile_freshness --tiles-url http://localhost:3000/tiles
Exits non-zero when the tile server serves a stale tile.
"""

import uuid
from datetime import timedelta

import requests
from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from capaggregator.alerts.models import Alert, AlertInfo, EventChain, ResolvedAlert
from capaggregator.ingestion.models import RawMessage
from capaggregator.sources.models import SourceAuthority

# Empty ocean, far from any real alert area, so a leaked row is obvious and harmless
PROBE_LON, PROBE_LAT = -35.0, -55.0
DEFAULT_TILES_URL = "http://capagg-martin:3000/tiles"
REQUEST_TIMEOUT = 15


class Command(BaseCommand):
    help = "Verify a running Martin re-renders a tile after the data behind it changes (no unbounded cache)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--tiles-url",
            default=DEFAULT_TILES_URL,
            help=(
                f"Base tile URL, Martin directly (default: {DEFAULT_TILES_URL}). Point this at Martin, "
                "not at nginx: nginx caches deliberately, with a TTL, and would fail this check for a minute."
            ),
        )

    def handle(self, *args, **options):
        base = options["tiles_url"].rstrip("/")
        marker = f"tile-freshness-{uuid.uuid4().hex[:12]}"
        probe = self._create_probe(marker)

        try:
            # Filtering the tile to our own status + event marker isolates the
            # check from every other alert in the database
            params = {"status": "Test", "event": marker, "t": probe["t"].isoformat()}
            url = f"{base}/alerts/0/0/0"

            fresh = self._fetch(url, params)
            if marker.encode() not in fresh:
                raise CommandError(
                    f"Probe alert is active at t but missing from {url} — the tile server is not seeing "
                    "the database, or the tile function is out of date (run create_alerts_tile_function)."
                )
            self.stdout.write(f"Probe alert renders at t={params['t']} ({len(fresh)} bytes)")

            # Expire it, then ask for the exact same URL again
            ResolvedAlert.objects.filter(pk=probe["resolved"].pk).update(
                expires=probe["t"] - timedelta(days=3)
            )
            after = self._fetch(url, params)

            if marker.encode() in after:
                raise CommandError(
                    "STALE TILE: the same URL still renders an alert that expired 3 days before `t`. "
                    "A cache in front of the renderer is serving one render indefinitely — check "
                    "cache_size_mb in deploy/martin/config.yaml (Martin's own cache has no TTL)."
                )
        finally:
            self._delete_probe(probe)

        self.stdout.write(self.style.SUCCESS("Tile freshness OK — the same URL tracked the database change"))

    def _fetch(self, url, params):
        """Tile bytes; Martin answers 204 (not 200 with an empty body) when the
        query matches nothing, which is exactly the expected post-expiry result."""
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if response.status_code == 204:
            return b""
        if response.status_code != 200:
            raise CommandError(f"{url} returned HTTP {response.status_code}: {response.text[:200]}")
        return response.content

    @transaction.atomic
    def _create_probe(self, marker):
        """A throwaway chain + resolved alert, active at `t`. Reuses an existing
        authority: saving a SourceAuthority triggers the Mosquitto auth sync."""
        authority = SourceAuthority.objects.order_by("pk").first()
        if authority is None:
            raise CommandError("No SourceAuthority registered — nothing to hang a probe alert on.")

        t = timezone.now().replace(microsecond=0)
        raw = RawMessage.objects.create(
            authority=authority,
            transport="manual",
            xml=f"<alert><!-- {marker} --></alert>",
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            state="stored",
        )
        alert = Alert.objects.create(
            authority=authority,
            raw_message=raw,
            identifier=marker,
            sender=f"{marker}@example.invalid",
            sent=t - timedelta(hours=1),
            msg_type="Alert",
            status="Test",
            scope="Public",
        )
        AlertInfo.objects.create(
            alert=alert,
            language="en-US",
            categories=["Other"],
            event=marker,
            urgency="Unknown",
            severity="Unknown",
            certainty="Unknown",
            effective=t - timedelta(hours=1),
            expires=t + timedelta(hours=1),
        )
        chain = EventChain.objects.create(authority=authority, first_alert=alert, latest_alert=alert)
        alert.chain = chain
        alert.save(update_fields=["chain"])

        # A 2-degree box in open ocean
        box = Polygon.from_bbox((PROBE_LON - 1, PROBE_LAT - 1, PROBE_LON + 1, PROBE_LAT + 1))
        geom = MultiPolygon(box, srid=4326)
        resolved = ResolvedAlert.objects.create(
            chain=chain,
            authority=authority,
            latest_alert=alert,
            msg_type="Alert",
            status="Test",
            event=marker,
            categories=["Other"],
            urgency="Unknown",
            severity="Unknown",
            certainty="Unknown",
            languages=["en-US"],
            headline=marker,
            effective=t - timedelta(hours=1),
            expires=t + timedelta(hours=1),
            countries=[str(authority.country).lower()],
            geom=geom,
            centroid=Point(PROBE_LON, PROBE_LAT, srid=4326),
        )
        return {"t": t, "raw": raw, "alert": alert, "chain": chain, "resolved": resolved}

    def _delete_probe(self, probe):
        """Innermost-first: EventChain PROTECTs its alerts, Alert PROTECTs its raw message."""
        try:
            with transaction.atomic():
                probe["resolved"].delete()
                probe["chain"].delete()  # Alert.chain is SET_NULL
                probe["alert"].delete()  # cascades to its info block
                probe["raw"].delete()
        except Exception as exc:  # never mask the real failure with a cleanup error
            self.stderr.write(self.style.WARNING(f"Probe cleanup failed ({exc}) — look for rows matching the marker"))
