"""fetch_wmo_registry mirrors sources.feeds' requests conventions (timeout,
User-Agent) and caches the raw response in Redis with a ~1 hour TTL so the
picker doesn't round-trip the network on every page load."""

from unittest.mock import Mock, patch

import requests
from django.core.cache import cache
from django.test import TestCase

from capaggregator.sources.wmo_registry import fetch_wmo_registry


class FetchWmoRegistryTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def _response(self, body: bytes = b"<rss></rss>"):
        response = Mock(status_code=200, content=body, headers={})
        response.raise_for_status = Mock()
        return response

    @patch("capaggregator.sources.wmo_registry.requests.get")
    def test_a_second_call_within_the_ttl_does_not_re_request(self, get):
        get.return_value = self._response()

        fetch_wmo_registry()
        fetch_wmo_registry()

        get.assert_called_once()

    @patch("capaggregator.sources.wmo_registry.requests.get")
    def test_returns_the_fetched_content_on_success(self, get):
        get.return_value = self._response(b"<rss>content</rss>")

        content, error = fetch_wmo_registry()

        self.assertEqual(content, b"<rss>content</rss>")
        self.assertIsNone(error)

    @patch("capaggregator.sources.wmo_registry.requests.get")
    def test_refresh_bypasses_and_repopulates_the_cache(self, get):
        get.side_effect = [self._response(b"<rss>first</rss>"), self._response(b"<rss>second</rss>")]

        fetch_wmo_registry()
        content, _error = fetch_wmo_registry(refresh=True)

        self.assertEqual(get.call_count, 2)
        self.assertEqual(content, b"<rss>second</rss>")
        # The repopulated cache serves the refreshed content on the next call.
        cached_content, _error = fetch_wmo_registry()
        self.assertEqual(cached_content, b"<rss>second</rss>")
        get.assert_called_with(
            "https://alertingauthority.wmo.int/rss.xml",
            timeout=15,
            headers={"User-Agent": "cap-aggregator/0.1 (+feed-poller)"},
        )

    @patch("capaggregator.sources.wmo_registry.requests.get")
    def test_an_unreachable_registry_surfaces_an_error_instead_of_raising(self, get):
        get.side_effect = requests.ConnectionError("boom")

        content, error = fetch_wmo_registry()

        self.assertIsNone(content)
        self.assertIsNotNone(error)
