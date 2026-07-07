"""Phase B/2: feed type (RSS/ATOM) is sniffed opportunistically while polling —
the feed is already fetched there, so no separate network call at save time."""

from unittest.mock import Mock, patch

from django.test import TestCase

from capaggregator.sources.feeds import fetch_feed

from .factories import create_source_authority


class FeedTypeDetectionTests(TestCase):
    def _response(self, body: bytes):
        response = Mock(status_code=200, content=body, headers={})
        response.raise_for_status = Mock()
        return response

    @patch("capaggregator.sources.feeds.requests.get")
    def test_fetch_feed_detects_rss_type_from_the_feed(self, get):
        get.return_value = self._response(
            b'<?xml version="1.0"?><rss version="2.0"><channel><title>t</title></channel></rss>'
        )
        authority = create_source_authority()

        fetch_feed(authority)

        self.assertEqual(authority.feed_type_detected, "rss")
