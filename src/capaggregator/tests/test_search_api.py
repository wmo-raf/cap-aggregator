"""Search API contract pieces the frontend depends on."""

from django.test import TestCase
from django.urls import reverse

from capaggregator.tests.factories import create_event_chain, create_source_authority


class SearchApiTests(TestCase):
    def test_results_carry_the_chain_id_for_detail_links(self):
        chain = create_event_chain(create_source_authority())

        response = self.client.get(reverse("alert_search"))

        self.assertEqual(response.status_code, 200)
        feature = response.json()["results"]["features"][0]
        self.assertEqual(feature["properties"]["chain"], chain.pk)
