"""Shared object factories for the test suite (reused across Phase B slices)."""

import uuid

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


def create_quarantined_message(authority=None, report=None, status="pending"):
    """A RawMessage + its QuarantinedMessage, without running the pipeline."""
    from capaggregator.ingestion.models import QuarantinedMessage, RawMessage

    if report is None:
        report = {"errors": [{"check": "sender", "message": "sender not registered"}], "warnings": []}
    raw = RawMessage.objects.create(
        authority=authority,
        transport="manual",
        xml="<alert/>",
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        state="quarantined",
    )
    return QuarantinedMessage.objects.create(raw_message=raw, report=report, status=status)
