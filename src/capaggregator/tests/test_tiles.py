"""The capagg_alerts_tile() Martin function source must be callable — a
regression guard for the varchar[] vs text[] overlap-operator bug that made
every tile request a 500."""

from django.core.management import call_command
from django.db import connection
from django.test import TestCase


class TileFunctionTests(TestCase):
    def setUp(self):
        call_command("create_alerts_tile_function")

    def test_tile_function_returns_bytes_even_with_a_category_filter(self):
        # The category/country filters compare ArrayField(CharField) columns
        # (varchar[]) against text[] filter arrays with `&&`. Before the ::text[]
        # cast, `varchar[] && text[]` had no operator and the query failed at
        # plan time — for every request, filtered or not, even on an empty table.
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT capagg_alerts_tile(0, 0, 0, %s::json)",
                ['{"category": "Met", "country": "ke"}'],
            )
            result = cursor.fetchone()[0]

        self.assertIsInstance(bytes(result), bytes)  # returns an (empty) MVT, not an error

    def test_tiles_carry_the_chain_id_for_detail_links(self):
        """Popups link to /alerts/<chain>/ — the MVT properties must include it."""
        from datetime import timedelta

        from django.contrib.gis.geos import MultiPolygon, Point, Polygon
        from django.utils import timezone

        from capaggregator.tests.factories import create_event_chain, create_source_authority

        geom = MultiPolygon(Polygon(((0, 0), (0, 20), (20, 20), (20, 0), (0, 0))))
        # backdate: inside the test transaction, Postgres now() is frozen at
        # transaction start, so a "now" effective time would never satisfy
        # effective <= now()
        past = timezone.now() - timedelta(hours=1)
        chain = create_event_chain(
            create_source_authority(),
            sent=past,
            infos=[{"effective": past, "expires": past + timedelta(days=1)}],
            resolved_kwargs={"geom": geom, "centroid": Point(10, 10)},
        )

        with connection.cursor() as cursor:
            cursor.execute("SELECT capagg_alerts_tile(0, 0, 0, '{}'::json)")
            tile = bytes(cursor.fetchone()[0])

        # MVT stores property keys/values as strings in the layer blob
        self.assertIn(b"chain", tile)
        self.assertIn(b"Flood Warning", tile)
        self.assertIsNotNone(chain.pk)
