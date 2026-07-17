"""Phase B/2: feed type (RSS/ATOM) is sniffed opportunistically while polling —
the feed is already fetched there, so no separate network call at save time.

Plus HTTP client hardening: each poll cycle reuses one keep-alive session for
the feed and all CAP XML fetches, with split connect/read timeouts and a
response-size cap so a misbehaving server can't hold a slot or balloon memory."""

from unittest.mock import Mock, patch

from django.test import TestCase

from capaggregator.ingestion.tasks import poll_feed
from capaggregator.sources.feeds import fetch_feed

from .factories import create_source_authority


def _response(body: bytes):
    response = Mock(status_code=200, headers={}, encoding="utf-8")
    response.raise_for_status = Mock()
    response.iter_content = Mock(return_value=iter([body]))
    return response


ATOM_WITH_TWO_ENTRIES = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>alerts</title>
  <entry><id>urn:alert:1</id>
    <link type="application/cap+xml" href="https://example.test/alerts/1.xml"/></entry>
  <entry><id>urn:alert:2</id>
    <link type="application/cap+xml" href="https://example.test/alerts/2.xml"/></entry>
</feed>"""

CAP_XML = b'<?xml version="1.0"?><alert xmlns="urn:oasis:names:tc:emergency:cap:1.2"></alert>'


class FeedTypeDetectionTests(TestCase):
    def _response(self, body: bytes):
        return _response(body)

    @patch("capaggregator.sources.feeds.requests.get")
    def test_fetch_feed_detects_rss_type_from_the_feed(self, get):
        get.return_value = self._response(
            b'<?xml version="1.0"?><rss version="2.0"><channel><title>t</title></channel></rss>'
        )
        authority = create_source_authority()

        fetch_feed(authority)

        self.assertEqual(authority.feed_type_detected, "rss")


class PollSessionTests(TestCase):
    @patch("capaggregator.ingestion.tasks.ingest_raw_message")
    @patch("capaggregator.sources.feeds.requests.Session")
    def test_one_keepalive_session_covers_the_feed_and_all_cap_fetches(self, session_cls, ingest):
        session = session_cls.return_value
        session.get.side_effect = [_response(ATOM_WITH_TWO_ENTRIES), _response(CAP_XML), _response(CAP_XML)]
        authority = create_source_authority()

        poll_feed.apply(args=[authority.id])

        self.assertEqual(session.get.call_count, 3)
        session.close.assert_called_once()
        self.assertEqual(ingest.delay.call_count, 2)

    @patch("capaggregator.ingestion.tasks.ingest_raw_message")
    @patch("capaggregator.sources.feeds.requests.Session")
    def test_session_is_closed_even_when_the_feed_fetch_fails(self, session_cls, ingest):
        session = session_cls.return_value
        session.get.side_effect = ConnectionError("refused")
        authority = create_source_authority()

        poll_feed.apply(args=[authority.id])

        session.close.assert_called_once()


class HardenedTransportTests(TestCase):
    @patch("capaggregator.sources.feeds.requests.get")
    def test_requests_use_split_connect_read_timeouts(self, get):
        get.return_value = _response(b"<rss version='2.0'><channel/></rss>")
        authority = create_source_authority()

        fetch_feed(authority)

        self.assertEqual(get.call_args.kwargs["timeout"], (5, 15))

    @patch("capaggregator.sources.feeds.requests.get")
    def test_an_oversized_response_is_rejected_mid_stream(self, get):
        # 11 x 1MB chunks: the reader must bail once past the cap instead of
        # buffering the whole body
        chunk = b"x" * (1024 * 1024)
        oversized = Mock(status_code=200, headers={}, encoding="utf-8")
        oversized.raise_for_status = Mock()
        oversized.iter_content = Mock(return_value=iter([chunk] * 11))
        get.return_value = oversized
        authority = create_source_authority()

        with self.assertRaises(Exception):
            fetch_feed(authority)

    @patch("capaggregator.sources.feeds.requests.get")
    def test_a_declared_oversized_content_length_is_rejected_before_reading(self, get):
        oversized = Mock(status_code=200, headers={"Content-Length": str(50 * 1024 * 1024)}, encoding="utf-8")
        oversized.raise_for_status = Mock()
        get.return_value = oversized
        authority = create_source_authority()

        with self.assertRaises(Exception):
            fetch_feed(authority)

        oversized.iter_content.assert_not_called()

    @patch("capaggregator.sources.feeds.requests.Session")
    def test_an_oversized_feed_counts_as_a_poll_failure(self, session_cls):
        session = session_cls.return_value
        oversized = Mock(status_code=200, headers={"Content-Length": str(50 * 1024 * 1024)}, encoding="utf-8")
        oversized.raise_for_status = Mock()
        session.get.return_value = oversized
        authority = create_source_authority()

        poll_feed.apply(args=[authority.id])

        authority.refresh_from_db()
        self.assertEqual(authority.feed_consecutive_failures, 1)
