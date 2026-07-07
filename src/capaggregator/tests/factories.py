"""Shared object factories for the test suite (reused across Phase B slices)."""

from capaggregator.sources.models import SourceAuthority

from .cap_samples import DEFAULT_SENDER


def create_source_authority(
    name="Test Authority",
    country="ke",
    sender_values=None,
    feed_url="https://example.test/rss.xml",
    **kwargs,
):
    return SourceAuthority.objects.create(
        name=name,
        country=country,
        sender_values=sender_values if sender_values is not None else [DEFAULT_SENDER],
        feed_url=feed_url,
        **kwargs,
    )
