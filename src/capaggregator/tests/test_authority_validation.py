"""Phase B/2: registering a Source Authority must be instant and safe — validation
does only local checks and never touches the network, so a slow or unreachable
feed cannot hang or fail the admin save."""

from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from capaggregator.sources.models import SourceAuthority

from .factories import create_source_authority


class AuthorityValidationTests(TestCase):
    def test_validation_makes_no_network_call(self):
        authority = create_source_authority(feed_url="https://unreachable.invalid/rss.xml")

        with patch("capaggregator.sources.feeds.requests.get", side_effect=AssertionError("network call")):
            authority.full_clean()  # must not raise, must not hit the network

    def test_validation_requires_at_least_one_sender_value(self):
        authority = SourceAuthority(name="X", country="ke", sender_values=[], feed_url="https://x.test/rss.xml")

        with self.assertRaises(ValidationError) as ctx:
            authority.full_clean()
        self.assertIn("sender_values", ctx.exception.message_dict)

    def test_validation_requires_a_feed_url(self):
        authority = SourceAuthority(name="X", country="ke", sender_values=["sender@x"], feed_url="")

        with self.assertRaises(ValidationError) as ctx:
            authority.full_clean()
        self.assertIn("feed_url", ctx.exception.message_dict)
