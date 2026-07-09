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
