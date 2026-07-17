"""Onboarding a feed (or catching up after an outage) must not cost
entries x round-trip: unknown entries' CAP XML is fetched through a bounded
greenlet pool, and one entry's failure never fails the poll or blocks the rest."""

from unittest.mock import patch

from django.test import TestCase

from capaggregator.ingestion import tasks
from capaggregator.ingestion.models import SourceEvent

from .factories import create_source_authority


def atom_feed(entry_count: int) -> bytes:
    entries = "".join(
        f'<entry><id>urn:alert:{n}</id>'
        f'<link type="application/cap+xml" href="https://example.test/alerts/{n}.xml"/></entry>'
        for n in range(entry_count)
    )
    return (
        '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">'
        f"<title>alerts</title>{entries}</feed>"
    ).encode()


class ParallelCapFetchTests(TestCase):
    @patch("capaggregator.ingestion.tasks.ingest_raw_message")
    @patch("capaggregator.sources.feeds.requests.Session")
    def test_a_backlog_is_fetched_concurrently_with_bounded_parallelism(self, session_cls, ingest):
        import gevent

        in_flight = {"now": 0, "max": 0}

        def tracking_fetch(url, session=None):
            in_flight["now"] += 1
            in_flight["max"] = max(in_flight["max"], in_flight["now"])
            gevent.sleep(0.005)  # yield so greenlets genuinely interleave
            in_flight["now"] -= 1
            return "<alert/>"

        authority = create_source_authority()
        with patch("capaggregator.sources.feeds.fetch_feed", return_value=(
            [{"id": f"urn:alert:{n}", "cap_url": f"https://example.test/alerts/{n}.xml"} for n in range(25)],
            True,
        )), patch("capaggregator.sources.feeds.fetch_cap_xml", side_effect=tracking_fetch):
            tasks.poll_feed.apply(args=[authority.id])

        self.assertEqual(ingest.delay.call_count, 25)
        self.assertEqual(in_flight["max"], 10)

    @patch("capaggregator.ingestion.tasks.ingest_raw_message")
    @patch("capaggregator.sources.feeds.requests.Session")
    def test_one_entrys_failure_is_skipped_without_failing_the_poll(self, session_cls, ingest):
        def flaky_fetch(url, session=None):
            if url.endswith("/1.xml"):
                raise ConnectionError("refused")
            return "<alert/>"

        authority = create_source_authority()
        with patch("capaggregator.sources.feeds.fetch_feed", return_value=(
            [{"id": f"urn:alert:{n}", "cap_url": f"https://example.test/alerts/{n}.xml"} for n in range(3)],
            True,
        )), patch("capaggregator.sources.feeds.fetch_cap_xml", side_effect=flaky_fetch):
            tasks.poll_feed.apply(args=[authority.id])

        self.assertEqual(ingest.delay.call_count, 2)
        event = SourceEvent.objects.filter(authority=authority, transport="poll").latest("occurred_at")
        self.assertTrue(event.ok)
        self.assertEqual(event.detail["entries_fetched"], 2)
        authority.refresh_from_db()
        self.assertEqual(authority.feed_consecutive_failures, 0)
